"""Perturbation study on the synthetic pages, without UIClip. Needs Chromium."""

from pathlib import Path

import pytest

from edufidelity.perturbations import (
    PERTURBATIONS,
    PerturbationRow,
    monotonicity,
    run_perturbations,
    verdicts,
    write_report,
)

pytestmark = pytest.mark.browser

PAGES = Path(__file__).resolve().parents[1] / "examples" / "pages"
SUBSET = [
    p
    for p in PERTURBATIONS
    if p.name in {"identity", "remove-essential", "shift-32px", "hue-180deg", "blank"}
]


@pytest.fixture(scope="module")
def rows(tmp_path_factory: pytest.TempPathFactory) -> list[PerturbationRow]:
    return run_perturbations(PAGES, tmp_path_factory.mktemp("pert"), perturbations=SUBSET)


def by(rows: list[PerturbationRow], page: str, name: str) -> PerturbationRow:
    return next(r for r in rows if r.page == page and r.perturbation.name == name)


def test_every_page_and_perturbation_is_measured(rows: list[PerturbationRow]) -> None:
    assert len(rows) == 3 * len(SUBSET)
    assert all(r.row.status == "ok" for r in rows)


@pytest.mark.parametrize("page", ["lesson", "quiz", "overview"])
def test_identity_is_a_perfect_copy(rows: list[PerturbationRow], page: str) -> None:
    row = by(rows, page, "identity").row
    assert row.ssim == pytest.approx(1.0, abs=1e-6)
    assert (row.ep_f1, row.ped_essential) == (1.0, 1.0)


@pytest.mark.parametrize("page", ["lesson", "quiz", "overview"])
def test_removing_an_essential_element_is_seen_in_its_category(
    rows: list[PerturbationRow], page: str
) -> None:
    row = by(rows, page, "remove-essential").row
    assert row.ped_essential is not None and row.ped_essential < 1.0
    assert row.ped_decorative == 1.0


@pytest.mark.parametrize("page", ["lesson", "quiz", "overview"])
def test_recoloring_leaves_structure_alone(rows: list[PerturbationRow], page: str) -> None:
    row = by(rows, page, "hue-180deg").row
    assert row.ep_f1 == 1.0
    assert row.layout_fidelity == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("page", ["lesson", "quiz", "overview"])
def test_blank_page_loses_every_element(rows: list[PerturbationRow], page: str) -> None:
    row = by(rows, page, "blank").row
    assert row.ep_f1 == 0.0
    assert row.ssim is not None and row.ssim < 1.0


def test_report_is_written_and_counts_checks(rows: list[PerturbationRow], tmp_path: Path) -> None:
    report = write_report(rows, tmp_path)
    text = report.read_text("utf-8")
    assert "Not results of the study" in text
    assert (tmp_path / "perturbations.csv").exists()
    assert (tmp_path / "lesson.png").exists()
    assert len(verdicts(rows)) == 3 * (len(SUBSET) - 1) * 7
    assert all(len(entry) == 4 for entry in monotonicity(rows))
