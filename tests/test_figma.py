"""Figma (REST file format) to Reference Design Representation. Synthetic JSON only."""

from typing import Any

import pytest

from edufidelity.figma import ExportRules, FigmaExportError, frame_to_reference
from edufidelity.models import ElementType


def node(id_: str, type_: str, x: float, y: float, w: float, h: float, **extra: Any) -> dict:
    return {
        "id": id_,
        "type": type_,
        "name": extra.pop("name", id_),
        "absoluteBoundingBox": {"x": x, "y": y, "width": w, "height": h},
        **extra,
    }


def document() -> dict:
    frame = node(
        "1:1",
        "FRAME",
        1000,
        2000,
        1280,
        800,
        name="Lesson 1",
        children=[
            node("1:2", "TEXT", 1064, 2040, 600, 40, characters="What can  be composted"),
            node(
                "1:3",
                "RECTANGLE",
                1064,
                2100,
                400,
                200,
                fills=[{"type": "IMAGE", "imageRef": "abc123"}],
                name="photo",
            ),
            node(
                "1:4",
                "INSTANCE",
                1064,
                2700,
                160,
                48,
                componentId="c1",
                name="Primary",
                children=[node("1:5", "TEXT", 1080, 2710, 120, 28, characters="Next lesson")],
            ),
            node(
                "1:6",
                "GROUP",
                1900,
                2040,
                40,
                40,
                name="logo",
                children=[node("1:7", "VECTOR", 1900, 2040, 40, 40)],
            ),
            node(
                "1:8",
                "FRAME",
                1064,
                2350,
                800,
                200,
                children=[
                    node("1:9", "TEXT", 1064, 2350, 800, 60, characters="Greens are moist."),
                    node("1:10", "TEXT", 1064, 2420, 800, 60, characters="hidden", visible=False),
                ],
            ),
            node("1:11", "RECTANGLE", 1000, 2000, 1280, 2, name="divider"),
            node("1:12", "TEXT", 1064, 2600, 0, 20, characters="zero width"),
        ],
    )
    return {
        "document": {
            "id": "0:0",
            "type": "DOCUMENT",
            "children": [{"id": "0:1", "type": "CANVAS", "children": [frame]}],
        },
        "components": {"c1": {"name": "Button/Primary"}},
    }


def test_elements_follow_the_collector_rules() -> None:
    ref = frame_to_reference(document(), "1:1", domain="synthetic")
    by_id = {e.id: e for e in ref.elements}
    assert set(by_id) == {"1:2", "1:3", "1:4", "1:6", "1:9"}
    assert by_id["1:2"].type is ElementType.TEXT and by_id["1:2"].text == "What can be composted"
    assert by_id["1:3"].type is ElementType.GRAPHIC and by_id["1:3"].asset == "abc123"
    assert by_id["1:4"].type is ElementType.CONTROL and by_id["1:4"].text == "Next lesson"
    assert by_id["1:6"].type is ElementType.GRAPHIC  # an icon drawn with vectors, as one leaf
    assert ref.interface_id == "Lesson 1" and (ref.frame_width, ref.frame_height) == (1280, 800)


def test_boxes_are_normalized_by_the_frame() -> None:
    title = next(e for e in frame_to_reference(document(), "1:1").elements if e.id == "1:2")
    assert title.bbox.x == pytest.approx(64 / 1280)
    assert title.bbox.y == pytest.approx(40 / 800)
    assert title.bbox.w == pytest.approx(600 / 1280)


def test_control_rule_is_configurable() -> None:
    rules = ExportRules(control_patterns=())  # no convention: nothing is a control
    ref = frame_to_reference(document(), "1:1", rules=rules)
    assert all(e.type is not ElementType.CONTROL for e in ref.elements)
    assert any(e.text == "Next lesson" and e.type is ElementType.TEXT for e in ref.elements)


def test_missing_frame_is_an_error() -> None:
    with pytest.raises(FigmaExportError, match="not found"):
        frame_to_reference(document(), "9:9")


def test_reference_has_no_salience_until_annotated() -> None:
    assert all(e.salience is None for e in frame_to_reference(document(), "1:1").elements)
