"""Keep only the content region of a reference frame.

A design frame may draw more than the interface under evaluation: for example the
learning platform (header, navigation, side panels) around the course content, which a
generated page never contains. Comparing against the whole frame would count the
platform as missing and offset every box. The region is declared per course, in frame
pixels, **before** annotation and measurement, and is recorded in the reference.

An element is kept when its center lies inside the region; boxes and the screenshot are
re-expressed relative to the region, and the generated page is then rendered at the
region's width.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .models import BBox, Reference


class RegionError(ValueError):
    """The region does not fit the frame, or leaves nothing to evaluate."""


def crop_reference(reference: Reference, region: tuple[int, int, int, int]) -> Reference:
    if reference.content_region is not None:
        raise RegionError("the reference is already cropped")
    rx, ry, rw, rh = region
    fw, fh = reference.frame_width, reference.frame_height
    if rw <= 0 or rh <= 0 or rx < 0 or ry < 0 or rx + rw > fw or ry + rh > fh:
        raise RegionError(f"region {region} does not fit the frame {fw}x{fh}")
    kept = []
    for element in reference.elements:
        b = element.bbox
        cx, cy = (b.x + b.w / 2) * fw, (b.y + b.h / 2) * fh
        if not (rx <= cx <= rx + rw and ry <= cy <= ry + rh):
            continue
        kept.append(
            element.model_copy(
                update={
                    "bbox": BBox(
                        x=(b.x * fw - rx) / rw,
                        y=(b.y * fh - ry) / rh,
                        w=b.w * fw / rw,
                        h=b.h * fh / rh,
                    )
                }
            )
        )
    if not kept:
        raise RegionError("no element of the reference lies inside the region")
    return reference.model_copy(
        update={"elements": kept, "frame_width": rw, "frame_height": rh, "content_region": region}
    )


def crop_screenshot(
    source: Path, region: tuple[int, int, int, int], target: Path, frame_width: int
) -> None:
    """Crop the reference screenshot; it may be exported at a multiple of the frame size."""
    with Image.open(source) as image:
        scale = image.width / frame_width
        rx, ry, rw, rh = (round(v * scale) for v in region)
        cropped = image.crop((rx, ry, rx + rw, ry + rh))
        if scale != 1:
            cropped = cropped.resize((region[2], region[3]), Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(target)
