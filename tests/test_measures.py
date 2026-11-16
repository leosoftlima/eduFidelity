"""Unit and property tests of the measures. No browser needed."""

from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

from edufidelity.matching import match_optimal
from edufidelity.measures import (
    element_preservation,
    layout_fidelity,
    pedagogical_preservation,
    ssim_score,
)
from edufidelity.models import BBox, Element, ElementType, RefElement, Salience

SALIENCES = list(Salience)


def make_reference(n: int) -> list[RefElement]:
    return [
        RefElement(
            id=f"r{i}",
            type=ElementType.TEXT,
            text=f"distinct sentence number {i}",
            salience=SALIENCES[i % 3],
            bbox=BBox(x=0.1, y=0.08 * i, w=0.5, h=0.05),
        )
        for i in range(n)
    ]


def copy_as_generated(reference: list[RefElement], dx: float = 0.0) -> list[Element]:
    return [
        Element(
            id=f"g{i}",
            type=e.type,
            text=e.text,
            asset=e.asset,
            bbox=BBox(x=e.bbox.x + dx, y=e.bbox.y, w=e.bbox.w, h=e.bbox.h),
        )
        for i, e in enumerate(reference)
    ]


def test_identical_page_scores_maximum() -> None:
    reference = make_reference(6)
    generated = copy_as_generated(reference)
    c = match_optimal(reference, generated)
    scores = element_preservation(c, len(reference), len(generated))
    assert (scores.precision, scores.recall, scores.f1) == (1.0, 1.0, 1.0)
    assert layout_fidelity(c, len(reference)) == pytest.approx(1.0)
    assert set(pedagogical_preservation(reference, c).values()) == {1.0}


def test_undefined_values_are_none_not_numbers() -> None:
    c = match_optimal([], [])
    scores = element_preservation(c, 0, 0)
    assert scores.precision is None and scores.recall is None and scores.f1 is None
    assert layout_fidelity(c, 0) is None
    only_essential = [e for e in make_reference(6) if e.salience is Salience.ESSENTIAL]
    ped = pedagogical_preservation(only_essential, match_optimal(only_essential, []))
    assert ped[Salience.ESSENTIAL] == 0.0
    assert ped[Salience.SUPPORTING] is None and ped[Salience.DECORATIVE] is None


def test_no_match_gives_zero_layout() -> None:
    reference = make_reference(3)
    c = match_optimal(reference, [])
    assert layout_fidelity(c, len(reference)) == 0.0
    assert element_preservation(c, len(reference), 0).f1 == 0.0


def test_displacement_lowers_layout_but_not_preservation() -> None:
    reference = make_reference(5)
    still = match_optimal(reference, copy_as_generated(reference))
    moved = match_optimal(reference, copy_as_generated(reference, dx=0.15))
    assert len(moved.matches) == len(still.matches) == 5
    assert layout_fidelity(moved, 5) < layout_fidelity(still, 5)  # type: ignore[operator]


@settings(max_examples=60, deadline=None)
@given(n=st.integers(min_value=1, max_value=9), data=st.data())
def test_removing_an_element_never_increases_preservation(n: int, data: st.DataObject) -> None:
    reference = make_reference(n)
    generated = copy_as_generated(reference)
    removed = data.draw(st.integers(min_value=0, max_value=n - 1))
    fewer = generated[:removed] + generated[removed + 1 :]

    before = match_optimal(reference, generated)
    after = match_optimal(reference, fewer)
    recall_before = element_preservation(before, n, len(generated)).recall
    recall_after = element_preservation(after, n, len(fewer)).recall
    assert recall_after is not None and recall_before is not None
    assert recall_after <= recall_before

    category = reference[removed].salience
    assert category is not None
    ped_after = pedagogical_preservation(reference, after)[category]
    assert ped_after is not None and ped_after < 1.0
    for other in Salience:
        if other is not category:
            assert pedagogical_preservation(reference, after)[other] in (None, 1.0)


def _save(path: Path, array: np.ndarray) -> Path:
    Image.fromarray(array).save(path)
    return path


def test_ssim_identity_and_padding(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    image = rng.integers(0, 255, size=(120, 200), dtype=np.uint8)
    a = _save(tmp_path / "a.png", image)
    assert ssim_score(a, a) == pytest.approx(1.0)

    truncated = _save(tmp_path / "short.png", image[:60])
    assert ssim_score(a, truncated) < 0.9
    assert ssim_score(a, truncated) == pytest.approx(ssim_score(truncated, a))


def test_iou() -> None:
    a = BBox(x=0, y=0, w=1, h=1)
    assert a.iou(a) == 1.0
    assert a.iou(BBox(x=2, y=2, w=1, h=1)) == 0.0
    assert a.iou(BBox(x=0.5, y=0, w=1, h=1)) == pytest.approx(1 / 3)
