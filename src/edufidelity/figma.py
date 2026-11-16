"""Reference Design Representation from a Figma frame (public REST file format).

Input: the JSON of a Figma file, as returned by ``GET /v1/files/:key`` (or a node from
``/v1/files/:key/nodes``), and the id of one frame. Output: a ``Reference`` with the
same element rules the DOM collector uses, so that both sides are comparable:

* **text**: a visible ``TEXT`` node; its text is ``characters``.
* **graphic**: a visible node with an ``IMAGE`` fill, or a vector-only group (an icon or
  illustration drawn in Figma). A graphic is a leaf.
* **control**: a node whose name or component name matches the control rule. A control
  is a leaf; its text is the text inside it. Figma has no notion of a control, so the
  rule is a naming convention (open question Q2). The default patterns are a
  PROVISIONAL proposal for the authors.
* hidden nodes (``visible: false``) and zero-area boxes are skipped; containers
  (frames, groups, sections) are not elements.

Boxes are normalized by the frame (x and width by its width, y and height by its
height). Asset keys are the ``imageRef`` of the image fill, so the same picture placed
twice has the same key.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .models import BBox, ElementType, RefElement, Reference

#: Provisional naming convention for controls (Q2). Case-insensitive, on node or
#: component names.
DEFAULT_CONTROL_PATTERNS = (
    r"\bbutton\b",
    r"\bbot[aã]o\b",
    r"\bbtn\b",
    r"\blink\b",
    r"\binput\b",
    r"\bcheckbox\b",
    r"\bradio\b",
    r"^control/",
)
# Lines and ellipses are left out: in HTML they are usually borders and rounded boxes,
# which the DOM collector does not report either.
_VECTOR_TYPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "REGULAR_POLYGON"}
_CONTAINER_TYPES = {"FRAME", "GROUP", "SECTION", "COMPONENT", "COMPONENT_SET", "INSTANCE"}


@dataclass
class ExportRules:
    control_patterns: Sequence[str] = DEFAULT_CONTROL_PATTERNS
    component_names: Mapping[str, str] = field(default_factory=dict)  # componentId -> name

    def is_control(self, node: Mapping[str, Any]) -> bool:
        names = [node.get("name", "")]
        if node.get("componentId"):
            names.append(self.component_names.get(node["componentId"], ""))
        return any(re.search(p, n, re.IGNORECASE) for p in self.control_patterns for n in names)


class FigmaExportError(ValueError):
    """The frame is missing or cannot be converted."""


def find_node(root: Mapping[str, Any], node_id: str) -> Mapping[str, Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        if node.get("id") == node_id:
            return node
        stack.extend(node.get("children", []))
    raise FigmaExportError(f"node {node_id!r} not found")


def _visible(node: Mapping[str, Any]) -> bool:
    return node.get("visible", True) is not False


def _image_ref(node: Mapping[str, Any]) -> str | None:
    for fill in node.get("fills", []) or []:
        if fill.get("type") == "IMAGE" and fill.get("visible", True) is not False:
            ref = fill.get("imageRef")
            return str(ref) if ref else "image"
    return None


def _only_vectors(node: Mapping[str, Any]) -> bool:
    children = [c for c in node.get("children", []) if _visible(c)]
    if not children:
        return False
    return all(
        c.get("type") in _VECTOR_TYPES or (c.get("type") in {"GROUP", "FRAME"} and _only_vectors(c))
        for c in children
    )


def _texts(node: Mapping[str, Any]) -> Iterator[str]:
    if not _visible(node):
        return
    if node.get("type") == "TEXT":
        yield str(node.get("characters", ""))
    for child in node.get("children", []):
        yield from _texts(child)


def _vector_key(node: Mapping[str, Any]) -> str:
    shape = repr(sorted((c.get("type", ""), c.get("name", "")) for c in node.get("children", [])))
    return hashlib.sha256(shape.encode("utf-8")).hexdigest()[:8]


def frame_to_reference(
    document: Mapping[str, Any],
    frame_id: str,
    *,
    interface_id: str | None = None,
    domain: str = "",
    course: str = "",
    rules: ExportRules | None = None,
) -> Reference:
    rules = rules or ExportRules(
        component_names={
            k: v.get("name", "") for k, v in (document.get("components") or {}).items()
        }
    )
    root = document.get("document", document)
    frame = find_node(root, frame_id)
    box = frame.get("absoluteBoundingBox")
    if not box or not box.get("width") or not box.get("height"):
        raise FigmaExportError(f"frame {frame_id!r} has no size")
    fx, fy, fw, fh = box["x"], box["y"], box["width"], box["height"]
    elements: list[RefElement] = []

    def add(node: Mapping[str, Any], kind: ElementType, text: str, asset: str | None) -> None:
        b = node.get("absoluteBoundingBox") or {}
        w, h = b.get("width", 0) or 0, b.get("height", 0) or 0
        if w <= 0 or h <= 0:
            return
        elements.append(
            RefElement(
                id=str(node["id"]),
                type=kind,
                text=" ".join(text.split()),
                asset=asset,
                bbox=BBox(x=(b["x"] - fx) / fw, y=(b["y"] - fy) / fh, w=w / fw, h=h / fh),
            )
        )

    def walk(node: Mapping[str, Any]) -> None:
        if not _visible(node):
            return
        kind = node.get("type")
        if kind != "TEXT" and rules.is_control(node):
            add(node, ElementType.CONTROL, " ".join(_texts(node)), None)
            return
        image = _image_ref(node)
        if image is not None:
            add(node, ElementType.GRAPHIC, str(node.get("name", "")), image)
            return
        if kind == "TEXT":
            add(node, ElementType.TEXT, str(node.get("characters", "")), None)
            return
        if kind in _VECTOR_TYPES or (kind in _CONTAINER_TYPES | {"GROUP"} and _only_vectors(node)):
            add(node, ElementType.GRAPHIC, str(node.get("name", "")), _vector_key(node))
            return
        for child in node.get("children", []):
            walk(child)

    for child in frame.get("children", []):
        walk(child)
    if not elements:
        raise FigmaExportError(f"frame {frame_id!r} has no visible elements")
    return Reference(
        interface_id=interface_id or str(frame.get("name", frame_id)),
        domain=domain,
        course=course,
        frame_width=round(fw),
        frame_height=round(fh),
        elements=elements,
    )
