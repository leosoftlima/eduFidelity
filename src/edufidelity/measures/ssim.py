"""Visual fidelity: SSIM between the reference and the generated screenshot."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from skimage.metrics import structural_similarity


def _load_gray(path: Path | str) -> NDArray[np.uint8]:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


def pad_to_common_canvas(
    a: NDArray[np.uint8], b: NDArray[np.uint8], fill: int = 255
) -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """Pad both images, anchored top-left, to the larger height and width.

    Screenshots are never resized: resizing distorts text and rewards a truncated
    page for being short. Padding makes missing length count as disagreement.
    """
    height, width = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])

    def pad(image: NDArray[np.uint8]) -> NDArray[np.uint8]:
        canvas = np.full((height, width), fill, dtype=np.uint8)
        canvas[: image.shape[0], : image.shape[1]] = image
        return canvas

    return pad(a), pad(b)


def ssim_score(reference_png: Path | str, generated_png: Path | str, fill: int = 255) -> float:
    """SSIM on grayscale with the settings of Wang et al. (2004).

    Gaussian window (sigma 1.5), population covariance, K1 = 0.01, K2 = 0.03.
    """
    ref, gen = pad_to_common_canvas(_load_gray(reference_png), _load_gray(generated_png), fill)
    score = structural_similarity(  # type: ignore[no-untyped-call]
        ref,
        gen,
        data_range=255,
        gaussian_weights=True,
        sigma=1.5,
        use_sample_covariance=False,
    )
    return float(score)
