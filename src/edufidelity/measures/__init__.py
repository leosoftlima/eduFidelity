"""Automatic fidelity evidence. Each measure is computed and reported on its own."""

from .salience import pedagogical_preservation
from .ssim import ssim_score
from .structure import StructuralScores, element_preservation, layout_fidelity
from .uiclip import UIClipComparison, UIClipScorer

__all__ = [
    "StructuralScores",
    "UIClipComparison",
    "UIClipScorer",
    "element_preservation",
    "layout_fidelity",
    "pedagogical_preservation",
    "ssim_score",
]
