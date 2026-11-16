"""Visual fidelity: UIClip embedding similarity between reference and generated screenshots.

UIClip (Wu et al., UIST 2024) is a CLIP model fine-tuned on user interface screenshots.
The measure is the cosine similarity of the two page embeddings.

Long pages. The encoder sees 224 x 224 pixels. Squashing a full-page screenshot into one
square, or center-cropping it as the default CLIP processor does, discards most of the
page. The model authors embed a screenshot as the **mean of square windows** slid along
its long side, after resizing the short side to 224 px; this module follows that
procedure exactly (``sliding_windows``), so the score is the one the checkpoint was
trained and validated with. Per-window similarities are kept as a diagnostic: the mean
embedding can hide a defect that is confined to one band of a long page.

Requires the optional extra: ``pip install edufidelity[uiclip]``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

#: Final UIClip checkpoint from the paper (web pairs + human pairs), pinned by revision.
UICLIP_CHECKPOINT = "biglab/uiclip_jitteredwebsites-2-224-paraphrased_webpairs_humanpairs"
UICLIP_REVISION = "505d4731b09263c07437a9022d23c800274da56b"
#: The checkpoint ships no processor; its authors use the original CLIP one.
PROCESSOR = "openai/clip-vit-base-patch32"
PROCESSOR_REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
WINDOW = 224

#: Maps a batch of square RGB windows to an (n, d) array of image features.
Embedder = Callable[[Sequence[Image.Image]], NDArray[np.float64]]


def preresize(image: Image.Image, size: int = WINDOW) -> Image.Image:
    """Resize so that the short side is ``size``, keeping the aspect ratio."""
    ratio = image.width / image.height
    if ratio > 1:
        return image.resize((int(ratio * size), size))
    return image.resize((size, int(size / ratio)))


def sliding_windows(image: Image.Image, size: int = WINDOW) -> list[Image.Image]:
    """Square windows along the long side, as in the UIClip reference code (MIT).

    The windows cover the whole page: the step is chosen so that the first window
    starts at the top and the last one ends at the bottom, overlapping when needed.
    """
    image = preresize(image.convert("RGB"), size)
    width, height = image.size
    square = min(width, height)
    longer = max(width, height)
    steps = (longer + square - 1) // square
    step = (longer - square) // (steps - 1) if steps > 1 else square
    windows = []
    for y in range(0, height - square + 1, step if height > width else square):
        for x in range(0, width - square + 1, step if width > height else square):
            windows.append(image.crop((x, y, x + square, y + square)))
    return windows


def _cosine(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denominator) if denominator > 0 else 0.0


@dataclass(frozen=True)
class PageEmbedding:
    mean: NDArray[np.float64]  # (d,) mean of the window features
    windows: NDArray[np.float64]  # (n, d) one row per window, top to bottom


@dataclass(frozen=True)
class UIClipComparison:
    similarity: float  # cosine of the mean embeddings: the measure
    band_similarities: list[float]  # window i of the reference against window i of the page
    reference_windows: int
    generated_windows: int

    @property
    def worst_band(self) -> float | None:
        return min(self.band_similarities) if self.band_similarities else None


@dataclass
class UIClipScorer:
    """Embeds screenshots with UIClip and compares them.

    ``embedder`` exists for tests and for other checkpoints; by default the pinned
    checkpoint is loaded on first use. Embeddings are cached by file content, so a
    reference compared with many generated pages is embedded once.
    """

    embedder: Embedder | None = None
    device: str | None = None
    batch_size: int = 32
    _cache: dict[str, PageEmbedding] = field(default_factory=dict, repr=False)
    _custom: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._custom = self.embedder is not None

    @property
    def checkpoint(self) -> str:
        if self._custom:
            return "custom"
        return f"{UICLIP_CHECKPOINT}@{UICLIP_REVISION[:7]}"

    def embed(self, png: Path | str) -> PageEmbedding:
        data = Path(png).read_bytes()
        key = hashlib.sha256(data).hexdigest()
        if key not in self._cache:
            with Image.open(png) as image:
                windows = sliding_windows(image)
            features = self._embedder()(windows)
            self._cache[key] = PageEmbedding(mean=features.mean(axis=0), windows=features)
        return self._cache[key]

    def compare(self, reference_png: Path | str, generated_png: Path | str) -> UIClipComparison:
        ref, gen = self.embed(reference_png), self.embed(generated_png)
        bands = [_cosine(r, g) for r, g in zip(ref.windows, gen.windows, strict=False)]
        return UIClipComparison(
            similarity=_cosine(ref.mean, gen.mean),
            band_similarities=bands,
            reference_windows=len(ref.windows),
            generated_windows=len(gen.windows),
        )

    def similarity(self, reference_png: Path | str, generated_png: Path | str) -> float:
        return self.compare(reference_png, generated_png).similarity

    def _embedder(self) -> Embedder:
        if self.embedder is None:
            self.embedder = _load_uiclip(self.device, self.batch_size)
        return self.embedder


def _load_uiclip(device: str | None, batch_size: int) -> Embedder:
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            "UIClip needs the optional extra: pip install 'edufidelity[uiclip]'"
        ) from error

    target = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model: Any = CLIPModel.from_pretrained(UICLIP_CHECKPOINT, revision=UICLIP_REVISION)
    model = model.eval().to(target)
    processor: Any = CLIPProcessor.from_pretrained(PROCESSOR, revision=PROCESSOR_REVISION)

    def embed(windows: Sequence[Image.Image]) -> NDArray[np.float64]:
        chunks = []
        for start in range(0, len(windows), batch_size):
            batch = list(windows[start : start + batch_size])
            inputs = processor(images=batch, return_tensors="pt")
            with torch.no_grad():
                features = model.get_image_features(pixel_values=inputs["pixel_values"].to(target))
            if not isinstance(features, torch.Tensor):  # newer transformers return an output
                features = features.pooler_output
            chunks.append(features.float().cpu().numpy().astype(np.float64))
        return np.concatenate(chunks, axis=0)

    return embed
