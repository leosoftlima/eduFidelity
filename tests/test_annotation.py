"""Human evaluation kit: agreement, salience sheets, blind assignment. No browser needed."""

import csv
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from edufidelity.annotation import (
    PageToRate,
    Rater,
    TaskBrief,
    apply_labels,
    assign,
    collect,
    krippendorff_alpha,
    read_sheet,
    resolve,
    write_sheet,
    write_sheets,
)
from edufidelity.annotation.assignment import AssignmentError
from edufidelity.annotation.salience import SheetError
from edufidelity.cli import main
from edufidelity.models import BBox, ElementType, RefElement, Reference, Salience

NAN = np.nan
#: Reliability data of Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability".
KRIPPENDORFF_2011 = [
    [1, 2, 3, 3, 2, 1, 4, 1, 2, NAN, NAN, NAN],
    [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, NAN, 3],
    [NAN, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, NAN],
    [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, NAN],
]


# ------------------------------------------------------------------ agreement


@pytest.mark.parametrize(
    ("level", "published"),
    [("nominal", 0.743), ("ordinal", 0.815), ("interval", 0.849), ("ratio", 0.797)],
)
def test_alpha_matches_the_published_values(level: str, published: float) -> None:
    alpha = krippendorff_alpha(KRIPPENDORFF_2011, level)  # type: ignore[arg-type]
    assert alpha == pytest.approx(published, abs=5e-4)


@pytest.mark.parametrize("level", ["nominal", "ordinal", "interval", "ratio"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_alpha_matches_the_reference_package(level: str, seed: int) -> None:
    import krippendorff

    rng = np.random.default_rng(seed)
    data = rng.integers(1, 6, size=(5, 40)).astype(float)
    data[rng.random(data.shape) < 0.2] = np.nan
    ours = krippendorff_alpha(data, level)  # type: ignore[arg-type]
    ref = krippendorff.alpha(reliability_data=data, level_of_measurement=level)
    assert ours == pytest.approx(ref, abs=1e-9)


def test_alpha_is_one_under_perfect_agreement_and_undefined_without_variation() -> None:
    assert krippendorff_alpha([[1, 2, 3], [1, 2, 3]], "ordinal") == pytest.approx(1.0)
    assert np.isnan(krippendorff_alpha([[2, 2, 2], [2, 2, 2]]))


# ------------------------------------------------------------------ salience sheets


def reference(n: int = 4) -> Reference:
    elements = [
        RefElement(
            id=f"e{i}",
            type=ElementType.TEXT,
            text=f"element {i}",
            bbox=BBox(x=0.1, y=0.1 * i, w=0.5, h=0.05),
        )
        for i in range(n)
    ]
    return Reference(interface_id="page", frame_width=1280, frame_height=800, elements=elements)


def fill(path: Path, labels: dict[str, str]) -> Path:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["salience"] = labels.get(row["element_id"], "")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


LABELS = {"e0": "essential", "e1": "supporting", "e2": "decorative", "e3": "essential"}


def test_sheet_round_trip(tmp_path: Path) -> None:
    ref = reference()
    write_sheet(ref, tmp_path / "ana.csv")
    labels = read_sheet(fill(tmp_path / "ana.csv", LABELS), ref)
    assert labels == {k: Salience(v) for k, v in LABELS.items()}


@pytest.mark.parametrize(
    ("change", "message"),
    [({"e1": ""}, "blank"), ({"e1": "important"}, "important")],
)
def test_bad_sheet_is_rejected(tmp_path: Path, change: dict[str, str], message: str) -> None:
    ref = reference()
    write_sheet(ref, tmp_path / "ana.csv")
    with pytest.raises(SheetError, match=message):
        read_sheet(fill(tmp_path / "ana.csv", {**LABELS, **change}), ref)


def test_sheet_with_a_missing_element_is_rejected(tmp_path: Path) -> None:
    write_sheet(reference(3), tmp_path / "ana.csv")
    fill(tmp_path / "ana.csv", LABELS)
    with pytest.raises(SheetError, match="'e3' missing"):
        read_sheet(tmp_path / "ana.csv", reference(4))


def test_majority_resolves_and_ties_go_to_adjudication() -> None:
    ref = reference()
    a = {k: Salience(v) for k, v in LABELS.items()}
    b = {**a, "e2": Salience.SUPPORTING}
    c = {**a, "e3": Salience.SUPPORTING}
    three = resolve(ref, {"a": a, "b": b, "c": c})
    assert three.complete and three.labels == a  # every element has a strict majority
    two = resolve(ref, {"a": a, "b": b})
    assert two.adjudication == ["e2"]
    with pytest.raises(SheetError, match="adjudication"):
        apply_labels(ref, two)
    decided = resolve(ref, {"a": a, "b": b}, adjudicated={"e2": Salience.DECORATIVE})
    labeled = apply_labels(ref, decided)
    assert [e.salience for e in labeled.elements] == [a[e] for e in ("e0", "e1", "e2", "e3")]
    assert labeled.digest() != ref.digest()


def test_resolution_reports_agreement() -> None:
    ref = reference()
    a = {k: Salience(v) for k, v in LABELS.items()}
    assert resolve(ref, {"a": a, "b": dict(a)}).alpha_nominal == pytest.approx(1.0)
    with pytest.raises(ValueError, match="two annotators"):
        resolve(ref, {"a": a})


def test_brief_renders_every_field() -> None:
    brief = TaskBrief(
        interface_id="quiz",
        function="assessment",
        objective="o",
        expected_action="act",
        completion_criterion="done",
    )
    text = brief.to_markdown()
    assert all(part in text for part in ("quiz", "assessment", "act", "done"))


# ------------------------------------------------------------------ blind assignment


def pages(n_interfaces: int = 6, per_interface: int = 3) -> list[PageToRate]:
    return [
        PageToRate(generated_id=f"i{i}-g{j}", interface_id=f"i{i}", domain="d")
        for i in range(n_interfaces)
        for j in range(per_interface)
    ]


RATERS = [
    Rater(rater_id=f"{group}{k}", group=group)
    for group in ("education", "design", "computing")
    for k in range(3)
]


def test_every_page_gets_each_perspective_once() -> None:
    result = assign(pages(), RATERS, seed=1)
    group_of = {r.rater_id: r.group for r in RATERS}
    for page in pages():
        groups = Counter(
            group_of[a.rater_id] for a in result if a.generated_id == page.generated_id
        )
        assert groups == {"education": 1, "design": 1, "computing": 1}


def test_annotators_never_rate_their_own_references() -> None:
    annotated = {"i0": {"education0", "design0"}, "i1": {"computing1"}}
    result = assign(pages(), RATERS, annotated, seed=3)
    for a in result:
        interface = a.generated_id.split("-")[0]
        assert a.rater_id not in annotated.get(interface, set())


def test_load_is_balanced_within_each_group() -> None:
    result = assign(pages(), RATERS, seed=5)
    load = Counter(a.rater_id for a in result)
    for group in ("education", "design", "computing"):
        counts = [load[r.rater_id] for r in RATERS if r.group == group]
        assert max(counts) - min(counts) <= 1


def test_assignment_is_reproducible_and_blind() -> None:
    first, again, other = (assign(pages(), RATERS, seed=s) for s in (9, 9, 10))
    assert first == again
    assert first != other
    codes = {a.code for a in first}
    assert len(codes) == len(pages())
    assert all("i" not in code.lower() for code in codes)  # no trace of the generated id


def test_impossible_constraints_are_an_error() -> None:
    every_designer = {"i0": {"design0", "design1", "design2"}}
    with pytest.raises(AssignmentError, match="design"):
        assign(pages(), RATERS, every_designer, seed=0)


def test_sheets_and_collection_round_trip(tmp_path: Path) -> None:
    result = assign(pages(2, 2), RATERS, seed=4)
    write_sheets(result, tmp_path)
    truth = {}
    for sheet in (tmp_path / "sheets").glob("*.csv"):
        with sheet.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert set(rows[0]) == {"position", "code", "rating", "comment"}
        for i, row in enumerate(rows):
            row["rating"] = "" if (sheet.stem == "design0" and i == 0) else str(1 + i % 5)
            truth[(sheet.stem, row["code"])] = row["rating"]
        with sheet.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    collected = collect(tmp_path)
    key = {a.code: a.generated_id for a in result}
    expected = {(r, key[c], int(v)) for (r, c), v in truth.items() if v}
    assert {(r.rater_id, r.generated_id, r.rating) for r in collected.ratings} == expected
    assert len(collected.missing) == 1 and collected.missing[0][0] == "design0"


def test_cli_assigns_and_collects(tmp_path: Path) -> None:
    measures = tmp_path / "measures.csv"
    with measures.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["interface_id", "generated_id", "domain", "status"])
        writer.writerows([p.interface_id, p.generated_id, p.domain, "ok"] for p in pages(3, 2))
        writer.writerow(["i9", "i9-broken", "d", "render_failure: timeout"])
    raters = tmp_path / "raters.csv"
    with raters.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rater_id", "group"])
        writer.writerows([r.rater_id, r.group] for r in RATERS)
    out = tmp_path / "rating"
    assert main(["assign-ratings", str(measures), str(raters), "--out", str(out)]) == 0
    assert not any("broken" in p.read_text("utf-8") for p in (out / "sheets").glob("*.csv"))
    assert main(["collect-ratings", str(out), "--out", str(tmp_path / "ratings.csv")]) == 0
    assert (tmp_path / "ratings.csv").read_text("utf-8").startswith("generated_id,rater_id")
