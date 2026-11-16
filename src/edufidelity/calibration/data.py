"""Calibration data: measurement rows of generated pages plus human ratings of them.

The unit of analysis is the generated page. Ratings are individual (one row per rater
and page); the clusters that resampling and validation respect are the reference
interface (several generated pages per reference) and the educational domain.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from ..models import MeasureRow

#: The six predictors of the composite. Decorative preservation is descriptive only.
PREDICTORS_6 = ("ssim", "uiclip", "ep_f1", "layout_fidelity", "ped_essential", "ped_supporting")
#: The ablation: the same model without the salience-conditioned predictors.
PREDICTORS_4 = ("ssim", "uiclip", "ep_f1", "layout_fidelity")


class Rating(BaseModel):
    generated_id: str
    rater_id: str
    rating: int = Field(ge=1)


@dataclass(frozen=True)
class CalibrationData:
    page_ids: NDArray[np.str_]
    interface: NDArray[np.str_]  # reference interface of each page
    domain: NDArray[np.str_]
    features: dict[str, NDArray[np.float64]]  # NaN where a measure is undefined
    rating_page: NDArray[np.int64]  # index into the page arrays, one entry per rating
    rating_level: NDArray[np.int64]  # 0 .. n_levels-1
    n_levels: int = 5

    @property
    def domains(self) -> list[str]:
        return sorted(set(self.domain.tolist()))

    def pages_matrix(self, predictors: Sequence[str]) -> NDArray[np.float64]:
        return np.column_stack([self.features[name] for name in predictors])

    def ratings_matrix(
        self, predictors: Sequence[str]
    ) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
        return self.pages_matrix(predictors)[self.rating_page], self.rating_level

    def human_mean(self) -> NDArray[np.float64]:
        """Mean rating of each page on the 1 .. n_levels scale (NaN if unrated)."""
        sums = np.bincount(self.rating_page, weights=self.rating_level + 1.0,
                           minlength=len(self.page_ids))
        counts = np.bincount(self.rating_page, minlength=len(self.page_ids))
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.asarray(sums / counts, dtype=np.float64)

    def subset(self, page_mask: NDArray[np.bool_]) -> CalibrationData:
        index = np.flatnonzero(page_mask)
        remap = np.full(len(self.page_ids), -1)
        remap[index] = np.arange(len(index))
        keep = page_mask[self.rating_page]
        return CalibrationData(
            page_ids=self.page_ids[index], interface=self.interface[index],
            domain=self.domain[index],
            features={k: v[index] for k, v in self.features.items()},
            rating_page=remap[self.rating_page[keep]], rating_level=self.rating_level[keep],
            n_levels=self.n_levels,
        )

    def take_interfaces(self, picks: Sequence[str]) -> CalibrationData:
        """Pages of the given interfaces, repeated as often as listed (bootstrap).

        A repeated interface becomes a distinct cluster (``id#2``) so that grouped
        cross-validation never splits its copies across folds.
        """
        parts: list[tuple[CalibrationData, str]] = []
        seen: dict[str, int] = {}
        for name in picks:
            seen[name] = seen.get(name, 0) + 1
            part = self.subset(self.interface == name)
            suffix = "" if seen[name] == 1 else f"#{seen[name]}"
            parts.append((part, suffix))
        return concatenate(parts, self.n_levels)


def concatenate(
    parts: Sequence[tuple[CalibrationData, str]], n_levels: int
) -> CalibrationData:
    offsets = np.cumsum([0] + [len(p.page_ids) for p, _ in parts])
    names = parts[0][0].features.keys()
    return CalibrationData(
        page_ids=np.concatenate([np.char.add(p.page_ids, s) for p, s in parts]),
        interface=np.concatenate([np.char.add(p.interface, s) for p, s in parts]),
        domain=np.concatenate([p.domain for p, _ in parts]),
        features={k: np.concatenate([p.features[k] for p, _ in parts]) for k in names},
        rating_page=np.concatenate([p.rating_page + o for (p, _), o in zip(parts, offsets,
                                                                             strict=False)]),
        rating_level=np.concatenate([p.rating_level for p, _ in parts]),
        n_levels=n_levels,
    )


def from_tables(
    rows: Sequence[MeasureRow], ratings: Sequence[Rating], n_levels: int = 5
) -> CalibrationData:
    """Join measurement rows and ratings. Rows that failed to render are excluded here
    on purpose and must be reported separately; ratings of unknown pages are an error."""
    usable = [r for r in rows if r.status == "ok"]
    position = {r.generated_id: i for i, r in enumerate(usable)}
    if len(position) != len(usable):
        raise ValueError("duplicated generated_id in the measurement rows")
    unknown = sorted({r.generated_id for r in ratings} - set(position))
    if unknown:
        raise ValueError(f"ratings for pages without measurements: {unknown[:5]}")
    if any(r.rating > n_levels for r in ratings):
        raise ValueError(f"ratings must be in 1..{n_levels}")

    def column(name: str) -> NDArray[np.float64]:
        values = [getattr(r, name) for r in usable]
        return np.array([np.nan if v is None else float(v) for v in values], dtype=np.float64)

    return CalibrationData(
        page_ids=np.array([r.generated_id for r in usable], dtype=np.str_),
        interface=np.array([r.interface_id for r in usable], dtype=np.str_),
        domain=np.array([r.domain for r in usable], dtype=np.str_),
        features={name: column(name) for name in PREDICTORS_6 + ("ped_decorative",)},
        rating_page=np.array([position[r.generated_id] for r in ratings], dtype=np.int64),
        rating_level=np.array([r.rating - 1 for r in ratings], dtype=np.int64),
        n_levels=n_levels,
    )
