"""Content region of a reference frame. No browser needed."""

from pathlib import Path

import pytest
from PIL import Image

from edufidelity.models import BBox, ElementType, RefElement, Reference
from edufidelity.region import RegionError, crop_reference, crop_screenshot


def framed() -> Reference:
    """A 1500 x 1000 frame: a platform header and sidebar around a content region."""

    def el(i: str, x: int, y: int, w: int, h: int) -> RefElement:
        return RefElement(
            id=i,
            type=ElementType.TEXT,
            text=i,
            bbox=BBox(x=x / 1500, y=y / 1000, w=w / 1500, h=h / 1000),
        )

    return Reference(
        interface_id="p",
        frame_width=1500,
        frame_height=1000,
        elements=[
            el("header", 0, 0, 1500, 80),
            el("sidebar", 0, 80, 60, 920),
            el("title", 100, 120, 600, 50),
            el("body", 100, 200, 1200, 300),
        ],
    )


def test_platform_elements_are_dropped_and_boxes_rebased() -> None:
    cropped = crop_reference(framed(), (60, 100, 1400, 900))
    assert [e.id for e in cropped.elements] == ["title", "body"]
    assert (cropped.frame_width, cropped.frame_height) == (1400, 900)
    title = cropped.elements[0].bbox
    assert title.x == pytest.approx(40 / 1400) and title.y == pytest.approx(20 / 900)
    assert title.w == pytest.approx(600 / 1400)
    assert cropped.content_region == (60, 100, 1400, 900)


def test_region_changes_the_digest_but_uncropped_digests_do_not_change() -> None:
    ref = framed()
    assert "content_region" not in ref.model_dump(mode="json") or ref.content_region is None
    assert crop_reference(ref, (60, 100, 1400, 900)).digest() != ref.digest()


@pytest.mark.parametrize("region", [(0, 0, 1600, 100), (-1, 0, 10, 10), (0, 0, 0, 10)])
def test_region_must_fit_the_frame(region: tuple[int, int, int, int]) -> None:
    with pytest.raises(RegionError):
        crop_reference(framed(), region)


def test_cropping_twice_is_refused() -> None:
    once = crop_reference(framed(), (60, 100, 1400, 900))
    with pytest.raises(RegionError, match="already"):
        crop_reference(once, (0, 0, 100, 100))


def test_screenshot_exported_at_2x_is_cropped_to_frame_pixels(tmp_path: Path) -> None:
    image = Image.new("RGB", (3000, 2000), "white")
    image.paste((255, 0, 0), (0, 0, 3000, 160))  # the header, in 2x pixels
    image.save(tmp_path / "frame.png")
    crop_screenshot(tmp_path / "frame.png", (60, 100, 1400, 900), tmp_path / "out.png", 1500)
    with Image.open(tmp_path / "out.png") as out:
        assert out.size == (1400, 900)
        assert out.getpixel((10, 10)) == (255, 255, 255)  # the red header was cut away
