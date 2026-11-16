"""UIClip measure: windowing and comparison logic, with a fake embedder.

The real checkpoint is exercised only by tests marked ``uiclip`` (optional extra).
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from edufidelity.measures.uiclip import UIClipScorer, preresize, sliding_windows


def color_embedder(windows: Sequence[Image.Image]) -> NDArray[np.float64]:
    """Mean RGB of each window, plus a constant so that black is not the zero vector."""
    return np.array([[*np.asarray(w, dtype=np.float64).mean(axis=(0, 1)), 1.0] for w in windows])


def save(image: Image.Image, path: Path) -> Path:
    image.save(path)
    return path


@pytest.mark.parametrize(
    ("size", "expected"),
    [((224, 224), 1), ((1280, 800), 2), ((1280, 1280), 1), ((1280, 4000), 4), ((800, 3000), 4)],
)
def test_windows_cover_the_page_with_squares(size: tuple[int, int], expected: int) -> None:
    windows = sliding_windows(Image.new("RGB", size, "white"))
    assert len(windows) == expected
    assert all(w.size == (224, 224) for w in windows)


def test_windows_reach_both_ends_of_a_tall_page() -> None:
    page = Image.new("RGB", (1280, 4000), "white")
    page.paste((255, 0, 0), (0, 0, 1280, 40))  # red band at the top
    page.paste((0, 0, 255), (0, 3960, 1280, 4000))  # blue band at the bottom
    windows = sliding_windows(page)
    top, bottom = np.asarray(windows[0]), np.asarray(windows[-1])
    assert top[0, 0, 0] > 200 and top[0, 0, 2] < 50
    assert bottom[-1, 0, 2] > 200 and bottom[-1, 0, 0] < 50


def test_preresize_keeps_the_short_side_at_224() -> None:
    assert min(preresize(Image.new("RGB", (1280, 3000))).size) == 224
    assert min(preresize(Image.new("RGB", (3000, 1280))).size) == 224


def test_identical_pages_score_one(tmp_path: Path) -> None:
    scorer = UIClipScorer(embedder=color_embedder)
    page = save(Image.new("RGB", (1280, 2000), (40, 120, 200)), tmp_path / "a.png")
    comparison = scorer.compare(page, page)
    assert comparison.similarity == pytest.approx(1.0)
    assert comparison.band_similarities == pytest.approx([1.0] * comparison.reference_windows)


def test_a_defect_in_one_band_shows_in_the_worst_band(tmp_path: Path) -> None:
    scorer = UIClipScorer(embedder=color_embedder)
    reference = Image.new("RGB", (1280, 4000), (240, 240, 240))
    damaged = reference.copy()
    damaged.paste((0, 0, 0), (0, 3000, 1280, 4000))  # only the bottom of the page changes
    comparison = scorer.compare(save(reference, tmp_path / "r.png"),
                                save(damaged, tmp_path / "g.png"))
    assert comparison.worst_band is not None
    assert comparison.worst_band < comparison.similarity < 1.0
    assert comparison.band_similarities[0] == pytest.approx(1.0)


def test_a_shorter_page_compares_the_bands_it_has(tmp_path: Path) -> None:
    scorer = UIClipScorer(embedder=color_embedder)
    long_page = save(Image.new("RGB", (1280, 4000), "white"), tmp_path / "long.png")
    short_page = save(Image.new("RGB", (1280, 1600), "white"), tmp_path / "short.png")
    comparison = scorer.compare(long_page, short_page)
    assert comparison.reference_windows > comparison.generated_windows
    assert len(comparison.band_similarities) == comparison.generated_windows


def test_embeddings_are_cached_by_content(tmp_path: Path) -> None:
    calls: list[int] = []

    def counting(windows: Sequence[Image.Image]) -> NDArray[np.float64]:
        calls.append(len(windows))
        return color_embedder(windows)

    scorer = UIClipScorer(embedder=counting)
    reference = save(Image.new("RGB", (1280, 800), "white"), tmp_path / "r.png")
    for i in range(3):
        page = save(Image.new("RGB", (1280, 800), (i * 50, 0, 0)), tmp_path / f"g{i}.png")
        scorer.similarity(reference, page)
    assert len(calls) == 4  # the reference once, each page once
    assert scorer.checkpoint == "custom"


@pytest.mark.uiclip
def test_real_checkpoint_separates_a_page_from_its_blank_version(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    page = Image.new("RGB", (1280, 900), "white")
    for i in range(8):  # stripes that stand in for content blocks
        page.paste((30 + 25 * i, 90, 160), (64, 60 + 100 * i, 900, 120 + 100 * i))
    scorer = UIClipScorer()
    same = scorer.similarity(save(page, tmp_path / "p.png"), tmp_path / "p.png")
    blank = scorer.similarity(tmp_path / "p.png",
                              save(Image.new("RGB", (1280, 900), "white"), tmp_path / "b.png"))
    assert same == pytest.approx(1.0, abs=1e-5)
    assert blank < same
    assert scorer.checkpoint.startswith("biglab/uiclip")


def test_checkpoint_of_the_default_scorer_is_the_pinned_one() -> None:
    scorer = UIClipScorer()
    assert scorer.checkpoint.startswith("biglab/uiclip") and "@505d473" in scorer.checkpoint

