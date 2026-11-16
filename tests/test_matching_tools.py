"""M4 tools: pair metrics, tuning, freezing, the review page and the synthetic sample."""

import json
from pathlib import Path

import pytest
from PIL import Image

from edufidelity.devsample import DEV_PERTURBATIONS, synthetic_dev_sample
from edufidelity.matching import match_optimal
from edufidelity.models import (
    BBox,
    Correspondence,
    DomSnapshot,
    Element,
    ElementType,
    Match,
    MatchConfig,
    RefElement,
    Reference,
)
from edufidelity.tuning import (
    GRID,
    FrozenMatching,
    OverlapError,
    configurations,
    freeze,
    load_config,
    tune,
)
from edufidelity.verification import (
    DevItem,
    PairScores,
    VerifiedPairs,
    load_dev_sample,
    pair_scores,
    pooled,
    review_page,
)

PAGES = Path(__file__).resolve().parents[1] / "examples" / "pages"


def text(i: str, words: str, y: float, cls: type = RefElement) -> Element:
    return cls(id=i, type=ElementType.TEXT, text=words, bbox=BBox(x=0.1, y=y, w=0.5, h=0.05))


def moved_item() -> DevItem:
    """One pair the provisional defaults reject: text slightly changed and moved far."""
    reference = Reference(interface_id="r", frame_width=1280, frame_height=800, elements=[
        text("a", "Compost needs greens and browns in balance", 0.1),
        text("b", "Turn the pile every week to add air", 0.3)])
    snapshot = DomSnapshot(frame_width=1280, frame_height=800, page_height=800, elements=[
        text("g1", "Compost needs greens and brown in balance!", 0.85, Element),
        text("g2", "Turn the pile every week to add air", 0.3, Element)])
    verified = VerifiedPairs(interface_id="r", generated_id="x", pairs=[("a", "g1"), ("b", "g2")],
                             verifier="test", source="manual")
    return DevItem(name="x", reference=reference, snapshot=snapshot, verified=verified)


def correspondence(pairs: list[tuple[str, str]]) -> Correspondence:
    return Correspondence(matches=[Match(ref_id=r, gen_id=g, cost=0, content_cost=0,
                                         spatial_cost=0, iou=1) for r, g in pairs],
                          missing=[], additional=[], method="t", config_digest="t")


def gold(pairs: list[tuple[str, str]]) -> VerifiedPairs:
    return VerifiedPairs(interface_id="r", generated_id="x", pairs=pairs, verifier="t",
                         source="manual")


def test_pair_scores_count_each_kind_of_error() -> None:
    s = pair_scores(correspondence([("a", "1"), ("b", "9")]), gold([("a", "1"), ("b", "2"),
                                                                    ("c", "3")]))
    assert (s.true_positive, s.false_positive, s.false_negative) == (1, 1, 2)
    assert s.precision == pytest.approx(0.5) and s.recall == pytest.approx(1 / 3)
    assert pooled([s, s]).true_positive == 2


def test_undefined_scores_are_none_not_zero() -> None:
    empty = PairScores(0, 0, 0)
    assert empty.precision is None and empty.recall is None and empty.f1 is None


def test_grid_keeps_the_weights_complementary() -> None:
    configs = configurations()
    assert len(configs) == len(GRID["text_similarity_floor"]) * len(GRID["max_cost"]) * len(
        GRID["content_weight"])
    assert all(c.content_weight + c.spatial_weight == pytest.approx(1.0) for c in configs)


def test_tuning_finds_a_configuration_that_recovers_the_lost_pair() -> None:
    result = tune([moved_item()])
    assert result.default_scores.recall == pytest.approx(0.5)
    assert result.best_scores.f1 == pytest.approx(1.0)
    assert result.best.max_cost > MatchConfig().max_cost


def test_ties_go_to_the_defaults() -> None:
    item = moved_item()
    easy = item.model_copy(update={"verified": gold([("b", "g2")])})
    snapshot = DomSnapshot(frame_width=1280, frame_height=800, page_height=800,
                           elements=[item.snapshot.elements[1]])
    easy = easy.model_copy(update={"snapshot": snapshot,
                                   "reference": item.reference.model_copy(
                                       update={"elements": [item.reference.elements[1]]})})
    assert tune([easy]).best == MatchConfig()


def test_freezing_refuses_an_overlap_with_the_study() -> None:
    result = tune([moved_item()])
    with pytest.raises(OverlapError, match="r"):
        freeze(result, [moved_item()], study_interfaces={"r", "other"})


def test_frozen_file_round_trips_and_detects_tampering(tmp_path: Path) -> None:
    frozen = freeze(tune([moved_item()]), [moved_item()], study_interfaces={"other"})
    path = tmp_path / "frozen.json"
    path.write_text(frozen.model_dump_json(), encoding="utf-8")
    assert load_config(path) == frozen.config
    data = json.loads(path.read_text("utf-8"))
    data["config"]["max_cost"] = 0.99
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        load_config(path)
    assert FrozenMatching.model_validate(json.loads(frozen.model_dump_json())).n_pairs == 2


def test_unverified_item_is_reported(tmp_path: Path) -> None:
    (tmp_path / "item").mkdir()
    with pytest.raises(ValueError, match="unverified items"):
        load_dev_sample(tmp_path)


@pytest.mark.browser
def test_review_page_saves_the_verified_pairs(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    item = moved_item()
    for name in ("r.png", "g.png"):
        Image.new("RGB", (1280, 800), "white").save(tmp_path / name)
    proposed = match_optimal(item.reference.elements, item.snapshot.elements)
    page_path = tmp_path / "review.html"
    page_path.write_text(review_page(item.reference, item.snapshot, proposed, tmp_path / "r.png",
                                     tmp_path / "g.png", "x"), encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(page_path.as_uri())
        page.fill("#verifier", "tester")
        page.select_option('tr[data-ref="a"] select', "g1")  # the pair the matcher missed
        with page.expect_download() as download:
            page.click("#save")
        saved = Path(download.value.path()).read_text("utf-8")
        browser.close()
    verified = VerifiedPairs.model_validate_json(saved)
    assert sorted(verified.pairs) == [("a", "g1"), ("b", "g2")]
    assert verified.verifier == "tester" and verified.source == "manual"


@pytest.mark.browser
def test_synthetic_sample_knows_the_true_pairs(tmp_path: Path) -> None:
    chosen = [p for p in DEV_PERTURBATIONS
              if p.name in {"identity", "swap-essential", "reword-essential", "blank"}]
    synthetic_dev_sample(PAGES, tmp_path / "build", tmp_path / "dev", chosen)
    items = {i.name: i for i in load_dev_sample(tmp_path / "dev")}
    assert len(items) == 3 * len(chosen)
    identity = items["lesson--identity"]
    assert len(identity.verified.pairs) == len(identity.reference.elements)
    assert items["lesson--blank"].verified.pairs == []
    for item in items.values():
        found = match_optimal(item.reference.elements, item.snapshot.elements)
        assert pair_scores(found, item.verified).false_positive == 0
    assert (tmp_path / "dev" / "quiz--swap-essential" / "review.html").exists()
