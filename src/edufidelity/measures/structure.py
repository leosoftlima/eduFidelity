"""Structural fidelity: Element Preservation and Layout Fidelity."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Correspondence


@dataclass(frozen=True)
class StructuralScores:
    precision: float | None
    recall: float | None
    f1: float | None


def element_preservation(
    correspondence: Correspondence, n_reference: int, n_generated: int
) -> StructuralScores:
    """Element-level precision, recall and F1 over accepted correspondences.

    Recall is undefined without eligible reference elements, precision without
    generated elements. Undefined values are ``None``, never 0 or 1.
    """
    matched = len(correspondence.matches)
    precision = matched / n_generated if n_generated else None
    recall = matched / n_reference if n_reference else None
    if n_reference == 0:
        f1 = None
    elif matched == 0:
        f1 = 0.0
    else:
        assert precision is not None and recall is not None
        f1 = 2 * precision * recall / (precision + recall)
    return StructuralScores(precision, recall, f1)


def layout_fidelity(correspondence: Correspondence, n_reference: int) -> float | None:
    """Mean IoU of normalized boxes over accepted correspondences.

    Zero when eligible reference elements exist but none was matched; undefined
    when there is nothing to match against.
    """
    if n_reference == 0:
        return None
    if not correspondence.matches:
        return 0.0
    return sum(m.iou for m in correspondence.matches) / len(correspondence.matches)
