"""One-to-one correspondence between reference elements and rendered elements.

Two methods:

* ``optimal``: minimum-cost assignment (Hungarian) over a cost that combines content
  and spatial disagreement, gated by element type.
* ``greedy_iou``: a deliberately simple baseline that pairs by descending IoU. It is
  kept so that the contribution of the cost model can be measured, not assumed.

Identifiers are never used as evidence: a generated page carries no knowledge of the
reference ids.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from .models import Correspondence, Element, ElementType, Match, MatchConfig, RefElement

_FORBIDDEN = 1e6


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def content_cost(ref: Element, gen: Element, config: MatchConfig) -> float:
    """Disagreement in [0, 1] between what two same-type elements carry."""
    if ref.type is ElementType.GRAPHIC:
        if ref.asset is None or gen.asset is None:
            return config.unknown_asset_cost
        return 0.0 if ref.asset == gen.asset else 1.0
    a, b = normalize_text(ref.text), normalize_text(gen.text)
    if not a and not b:
        return config.unknown_asset_cost
    # Character-level similarity has a high floor: two unrelated sentences in the same
    # language still share many characters. Similarity at or below the floor counts as
    # none, so "same place, different text" is not mistaken for the same element.
    similarity = fuzz.ratio(a, b) / 100.0
    floor = config.text_similarity_floor
    return 1.0 - max(0.0, (similarity - floor) / (1.0 - floor))


def spatial_cost(ref: Element, gen: Element, config: MatchConfig) -> float:
    """Disagreement in [0, 1]: half overlap, half center distance.

    IoU alone is zero for every non-overlapping pair, which cannot rank a small
    displacement above a large one; the center-distance term does.
    """
    iou = ref.bbox.iou(gen.bbox)
    (ax, ay), (bx, by) = ref.bbox.center, gen.bbox.center
    distance = min(1.0, math.hypot(ax - bx, ay - by) / config.center_distance_scale)
    return 0.5 * (1.0 - iou) + 0.5 * distance


def pair_cost(ref: Element, gen: Element, config: MatchConfig) -> tuple[float, float, float]:
    content = content_cost(ref, gen, config)
    spatial = spatial_cost(ref, gen, config)
    total = config.content_weight * content + config.spatial_weight * spatial
    return total, content, spatial


def match_optimal(
    reference: Sequence[RefElement],
    generated: Sequence[Element],
    config: MatchConfig | None = None,
) -> Correspondence:
    config = config or MatchConfig()
    matches: list[Match] = []
    if reference and generated:
        cost = np.full((len(reference), len(generated)), _FORBIDDEN)
        parts: dict[tuple[int, int], tuple[float, float]] = {}
        for i, ref in enumerate(reference):
            for j, gen in enumerate(generated):
                if ref.type is not gen.type:
                    continue
                total, content, spatial = pair_cost(ref, gen, config)
                cost[i, j] = total
                parts[(i, j)] = (content, spatial)
        rows, cols = linear_sum_assignment(cost)
        for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
            if cost[i, j] > config.max_cost:
                continue
            content, spatial = parts[(i, j)]
            matches.append(
                Match(
                    ref_id=reference[i].id,
                    gen_id=generated[j].id,
                    cost=float(cost[i, j]),
                    content_cost=content,
                    spatial_cost=spatial,
                    iou=reference[i].bbox.iou(generated[j].bbox),
                )
            )
    return _finish(reference, generated, matches, "optimal", config)


def match_greedy_iou(
    reference: Sequence[RefElement],
    generated: Sequence[Element],
    min_iou: float = 0.5,
) -> Correspondence:
    candidates = sorted(
        (
            (ref.bbox.iou(gen.bbox), i, j)
            for i, ref in enumerate(reference)
            for j, gen in enumerate(generated)
            if ref.type is gen.type
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    used_ref: set[int] = set()
    used_gen: set[int] = set()
    matches: list[Match] = []
    for iou, i, j in candidates:
        if iou < min_iou:
            break
        if i in used_ref or j in used_gen:
            continue
        used_ref.add(i)
        used_gen.add(j)
        matches.append(
            Match(
                ref_id=reference[i].id,
                gen_id=generated[j].id,
                cost=1.0 - iou,
                content_cost=0.0,
                spatial_cost=1.0 - iou,
                iou=iou,
            )
        )
    return _finish(reference, generated, matches, f"greedy_iou@{min_iou}", MatchConfig())


def _finish(
    reference: Sequence[RefElement],
    generated: Sequence[Element],
    matches: list[Match],
    method: str,
    config: MatchConfig,
) -> Correspondence:
    matched_ref = {m.ref_id for m in matches}
    matched_gen = {m.gen_id for m in matches}
    return Correspondence(
        matches=sorted(matches, key=lambda m: m.ref_id),
        missing=[e.id for e in reference if e.id not in matched_ref],
        additional=[e.id for e in generated if e.id not in matched_gen],
        method=method,
        config_digest=config.digest(),
    )
