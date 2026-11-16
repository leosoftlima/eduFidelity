from edufidelity.matching import match_greedy_iou, match_optimal, normalize_text
from edufidelity.models import BBox, Element, ElementType, MatchConfig, RefElement, Salience


def ref(id: str, text: str, x: float, y: float, type: ElementType = ElementType.TEXT,
        asset: str | None = None) -> RefElement:
    return RefElement(id=id, type=type, text=text, asset=asset, salience=Salience.ESSENTIAL,
                      bbox=BBox(x=x, y=y, w=0.2, h=0.05))


def gen(id: str, text: str, x: float, y: float, type: ElementType = ElementType.TEXT,
        asset: str | None = None) -> Element:
    return Element(id=id, type=type, text=text, asset=asset, bbox=BBox(x=x, y=y, w=0.2, h=0.05))


def pairs(correspondence) -> dict[str, str]:
    return {m.ref_id: m.gen_id for m in correspondence.matches}


def test_identical_sets_match_completely() -> None:
    reference = [ref("a", "Question", 0.1, 0.1), ref("b", "Submit", 0.1, 0.5)]
    generated = [gen("g1", "Question", 0.1, 0.1), gen("g2", "Submit", 0.1, 0.5)]
    result = match_optimal(reference, generated)
    assert pairs(result) == {"a": "g1", "b": "g2"}
    assert result.missing == [] and result.additional == []


def test_swapped_positions_follow_content_not_place() -> None:
    reference = [ref("a", "First paragraph of the lesson", 0.1, 0.1),
                 ref("b", "Second and different paragraph", 0.1, 0.2)]
    generated = [gen("g1", "Second and different paragraph", 0.1, 0.1),
                 gen("g2", "First paragraph of the lesson", 0.1, 0.2)]
    assert pairs(match_optimal(reference, generated)) == {"a": "g2", "b": "g1"}


def test_duplicate_texts_are_resolved_by_position() -> None:
    reference = [ref("a", "Complete", 0.7, 0.1), ref("b", "Complete", 0.7, 0.3)]
    generated = [gen("g1", "Complete", 0.7, 0.3), gen("g2", "Complete", 0.7, 0.1)]
    assert pairs(match_optimal(reference, generated)) == {"a": "g2", "b": "g1"}


def test_types_never_cross() -> None:
    reference = [ref("a", "Submit", 0.1, 0.1, ElementType.CONTROL)]
    generated = [gen("g1", "Submit", 0.1, 0.1, ElementType.TEXT)]
    result = match_optimal(reference, generated)
    assert result.matches == [] and result.missing == ["a"] and result.additional == ["g1"]


def test_unrelated_content_far_away_is_rejected() -> None:
    reference = [ref("a", "Read the instructions carefully", 0.0, 0.0)]
    generated = [gen("g1", "Copyright notice", 0.7, 0.9)]
    assert match_optimal(reference, generated).matches == []


def test_graphics_match_by_asset() -> None:
    reference = [ref("a", "", 0.1, 0.1, ElementType.GRAPHIC, asset="logo"),
                 ref("b", "", 0.5, 0.1, ElementType.GRAPHIC, asset="chart")]
    generated = [gen("g1", "", 0.5, 0.1, ElementType.GRAPHIC, asset="logo"),
                 gen("g2", "", 0.1, 0.1, ElementType.GRAPHIC, asset="chart")]
    assert pairs(match_optimal(reference, generated)) == {"a": "g1", "b": "g2"}


def test_empty_sides() -> None:
    assert match_optimal([], [gen("g1", "x", 0, 0)]).additional == ["g1"]
    assert match_optimal([ref("a", "x", 0, 0)], []).missing == ["a"]


def test_greedy_baseline_fails_where_layout_moves() -> None:
    reference = [ref("a", "Tip: add dry leaves", 0.1, 0.1)]
    generated = [gen("g1", "Tip: add dry leaves", 0.4, 0.1)]
    assert match_greedy_iou(reference, generated).matches == []
    assert pairs(match_optimal(reference, generated)) == {"a": "g1"}


def test_config_digest_changes_with_parameters() -> None:
    assert MatchConfig().digest() == MatchConfig().digest()
    assert MatchConfig().digest() != MatchConfig(max_cost=0.4).digest()


def test_normalize_text() -> None:
    assert normalize_text("  Próxima\n LIÇÃO ") == "próxima lição"
