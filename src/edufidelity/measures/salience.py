"""Salience-conditioned preservation.

Salience belongs to reference elements and is fixed before any generated output is
seen. This module only conditions element preservation on it.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models import Correspondence, RefElement, Salience


def pedagogical_preservation(
    reference: Sequence[RefElement], correspondence: Correspondence
) -> dict[Salience, float | None]:
    """Share of reference elements with an accepted match, per salience category.

    A category with no eligible elements is missing by design (``None``).
    """
    matched = {m.ref_id for m in correspondence.matches}
    scores: dict[Salience, float | None] = {}
    for category in Salience:
        members = [e for e in reference if e.salience is category]
        scores[category] = (
            sum(e.id in matched for e in members) / len(members) if members else None
        )
    return scores
