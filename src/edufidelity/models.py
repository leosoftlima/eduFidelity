"""Data contracts shared by every stage.

All geometry is normalized by the dimensions of the *reference frame*, for reference
and generated elements alike, so that a generated page that grows taller than its
reference is not silently rescaled into agreement.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ElementType(StrEnum):
    TEXT = "text"
    GRAPHIC = "graphic"
    CONTROL = "control"


class Salience(StrEnum):
    ESSENTIAL = "essential"
    SUPPORTING = "supporting"
    DECORATIVE = "decorative"


class BBox(BaseModel):
    """Axis-aligned box, normalized by the reference frame (x, w by width; y, h by height)."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    w: float = Field(ge=0)
    h: float = Field(ge=0)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def iou(self, other: BBox) -> float:
        ix = max(0.0, min(self.x + self.w, other.x + other.w) - max(self.x, other.x))
        iy = max(0.0, min(self.y + self.h, other.y + other.h) - max(self.y, other.y))
        inter = ix * iy
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0


class Element(BaseModel):
    """An interface element, either from the reference or from a rendered page."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: ElementType
    text: str = ""
    bbox: BBox
    asset: str | None = None  # stable key of the visual asset, when one exists


class RefElement(Element):
    salience: Salience | None = None


class Reference(BaseModel):
    """Reference Design Representation of one interface."""

    interface_id: str
    domain: str = ""
    course: str = ""
    frame_width: int
    frame_height: int
    elements: list[RefElement]

    def digest(self) -> str:
        return _digest(self.model_dump(mode="json"))


class DomSnapshot(BaseModel):
    """Elements collected from a rendered page, normalized by the reference frame."""

    frame_width: int
    frame_height: int
    page_height: int
    elements: list[Element]


class RenderRecord(BaseModel):
    status: Literal["ok", "render_failure"]
    reason: str = ""
    browser: str = ""
    viewport_width: int
    viewport_height: int
    stable_after_ms: int = 0
    screenshot: str | None = None


class MatchConfig(BaseModel):
    """Matching parameters.

    The defaults are PROVISIONAL. They will be tuned on a development sample with
    manually verified correspondences and then frozen; the digest is stored with
    every measurement so that results can be traced to the exact configuration.
    """

    model_config = ConfigDict(frozen=True)

    content_weight: float = 0.5
    spatial_weight: float = 0.5
    unknown_asset_cost: float = 0.5
    text_similarity_floor: float = 0.5
    center_distance_scale: float = 0.5
    max_cost: float = 0.5

    def digest(self) -> str:
        return _digest(self.model_dump(mode="json"))


class Match(BaseModel):
    ref_id: str
    gen_id: str
    cost: float
    content_cost: float
    spatial_cost: float
    iou: float


class Correspondence(BaseModel):
    matches: list[Match]
    missing: list[str]  # reference elements without an accepted match
    additional: list[str]  # generated elements without an accepted match
    method: str
    config_digest: str


class MeasureRow(BaseModel):
    """One row of automatic evidence. Measures are kept separate; no composite here."""

    interface_id: str
    generated_id: str
    status: str = "ok"
    ssim: float | None = None
    uiclip: float | None = None
    ep_precision: float | None = None
    ep_recall: float | None = None
    ep_f1: float | None = None
    layout_fidelity: float | None = None
    ped_essential: float | None = None
    ped_supporting: float | None = None
    ped_decorative: float | None = None
    n_reference: int = 0
    n_generated: int = 0
    n_matched: int = 0
    config_digest: str = ""
    reference_digest: str = ""


def _digest(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
