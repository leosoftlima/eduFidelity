"""Tune the matching parameters on a verified development sample, then freeze them.

* ``evaluate`` scores one configuration: pair precision, recall and F1, pooled over
  every page of the development sample.
* ``tune`` evaluates a grid and picks the best F1. Ties go to the configuration
  closest to the provisional defaults, so the choice is deterministic and conservative.
* ``freeze`` writes the chosen configuration with three digests (configuration,
  development sample, and the frozen file itself) and refuses a development sample
  that shares any reference interface with the study.

Measurements made with a frozen file carry its configuration digest in every row.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .matching import match_greedy_iou, match_optimal
from .models import MatchConfig
from .verification import DevItem, PairScores, pair_scores, pooled, sample_digest

GRID: dict[str, tuple[float, ...]] = {
    "text_similarity_floor": (0.3, 0.4, 0.5, 0.6, 0.7),
    "max_cost": (0.3, 0.4, 0.5, 0.6, 0.7),
    "content_weight": (0.3, 0.5, 0.7),
}


def evaluate(config: MatchConfig, items: Sequence[DevItem]) -> PairScores:
    return pooled(
        [
            pair_scores(
                match_optimal(i.reference.elements, i.snapshot.elements, config), i.verified
            )
            for i in items
        ]
    )


def evaluate_baseline(items: Sequence[DevItem], min_iou: float = 0.5) -> PairScores:
    return pooled(
        [
            pair_scores(
                match_greedy_iou(i.reference.elements, i.snapshot.elements, min_iou), i.verified
            )
            for i in items
        ]
    )


def configurations(grid: Mapping[str, Iterable[float]] = GRID) -> list[MatchConfig]:
    names = list(grid)
    out = []
    for values in itertools.product(*(tuple(grid[n]) for n in names)):
        settings: dict[str, Any] = dict(zip(names, values, strict=True))
        if "content_weight" in settings:
            settings["spatial_weight"] = round(1.0 - settings["content_weight"], 10)
        out.append(MatchConfig(**settings))
    return out


def _distance_to_default(config: MatchConfig) -> float:
    default = MatchConfig().model_dump()
    return float(sum(abs(v - default[k]) for k, v in config.model_dump().items()))


@dataclass(frozen=True)
class TuningResult:
    rows: list[tuple[MatchConfig, PairScores]]
    best: MatchConfig
    best_scores: PairScores
    default_scores: PairScores
    baseline_scores: PairScores


def tune(items: Sequence[DevItem], grid: Mapping[str, Iterable[float]] = GRID) -> TuningResult:
    rows = [(config, evaluate(config, items)) for config in configurations(grid)]
    best, best_scores = min(
        rows, key=lambda r: (-(r[1].f1 or 0.0), _distance_to_default(r[0]), r[0].digest())
    )
    return TuningResult(
        rows, best, best_scores, evaluate(MatchConfig(), items), evaluate_baseline(items)
    )


class FrozenMatching(BaseModel):
    """The configuration every study measurement must use."""

    config: MatchConfig
    config_digest: str
    dev_sample_digest: str
    dev_sources: list[str]  # manual and/or synthetic
    n_items: int
    n_pairs: int
    precision: float | None
    recall: float | None
    f1: float | None
    frozen_at: str
    note: str = ""


class OverlapError(ValueError):
    """The development sample shares reference interfaces with the study."""


def freeze(
    result: TuningResult,
    items: Sequence[DevItem],
    study_interfaces: set[str],
    note: str = "",
) -> FrozenMatching:
    overlap = sorted({i.reference.interface_id for i in items} & study_interfaces)
    if overlap:
        raise OverlapError(f"development sample overlaps the study: {', '.join(overlap)}")
    return FrozenMatching(
        config=result.best,
        config_digest=result.best.digest(),
        dev_sample_digest=sample_digest(items),
        dev_sources=sorted({i.verified.source for i in items}),
        n_items=len(items),
        n_pairs=sum(len(i.verified.pairs) for i in items),
        precision=result.best_scores.precision,
        recall=result.best_scores.recall,
        f1=result.best_scores.f1,
        frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
        note=note,
    )


def load_config(path: Path) -> MatchConfig:
    """A frozen file, or a plain MatchConfig JSON."""
    data = json.loads(path.read_text("utf-8"))
    if "config" in data:
        frozen = FrozenMatching.model_validate(data)
        if frozen.config.digest() != frozen.config_digest:
            raise ValueError(f"{path}: configuration does not match its digest")
        return frozen.config
    return MatchConfig.model_validate(data)


def _fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f}"


def report(result: TuningResult, items: Sequence[DevItem], banner: str) -> str:
    sources = ", ".join(sorted({i.verified.source for i in items}))
    lines = [
        "# Matching: tuning on the development sample",
        "",
        banner,
        "",
        f"{len(items)} generated pages, {sum(len(i.verified.pairs) for i in items)} verified "
        f"pairs (source: {sources}). Development sample digest `{sample_digest(items)}`.",
        "",
        "| Matcher | Pair precision | Pair recall | Pair F1 |",
        "|---|---:|---:|---:|",
    ]
    for label, s in (
        ("Greedy IoU baseline (IoU ≥ 0.5)", result.baseline_scores),
        ("Optimal, provisional defaults", result.default_scores),
        ("Optimal, best on the grid", result.best_scores),
    ):
        lines.append(f"| {label} | {_fmt(s.precision)} | {_fmt(s.recall)} | {_fmt(s.f1)} |")
    best = result.best
    top = result.best_scores.f1 or 0.0
    ties = sum((s.f1 or 0.0) >= top - 1e-12 for _, s in result.rows)
    lines += [
        "",
        "Best configuration "
        f"(digest `{best.digest()}`): text similarity floor {best.text_similarity_floor}, "
        f"maximum cost {best.max_cost}, content weight {best.content_weight}, "
        f"spatial weight {best.spatial_weight}. Ties are broken toward the defaults.",
        "",
        f"{ties} of {len(result.rows)} configurations reach the best F1. When many tie, the "
        "sample cannot tell them apart, and the choice falls back to the defaults.",
        "",
        f"## Every configuration ({len(result.rows)})",
        "",
        "| Text floor | Max cost | Content weight | Precision | Recall | F1 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for config, s in sorted(result.rows, key=lambda r: -(r[1].f1 or 0.0)):
        lines.append(
            f"| {config.text_similarity_floor} | {config.max_cost} | "
            f"{config.content_weight} | {_fmt(s.precision)} | {_fmt(s.recall)} | "
            f"{_fmt(s.f1)} |"
        )
    return "\n".join(lines) + "\n"
