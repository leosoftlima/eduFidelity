"""Krippendorff's alpha for nominal, ordinal, interval and ratio data.

Computed from the coincidence matrix (Krippendorff, 2011, "Computing Krippendorff's
Alpha-Reliability"). Missing values are allowed; units with fewer than two values are
not pairable and are ignored.

    alpha = 1 - D_o / D_e

``data`` is a coders x units matrix of numeric values with ``nan`` for missing. For
nominal data the numbers are only labels; for ordinal data only their order matters.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

Level = Literal["nominal", "ordinal", "interval", "ratio"]


def coincidences(data: ArrayLike) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return (values, coincidence matrix) over the values that occur in pairable units."""
    matrix = np.asarray(data, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("data must be a coders x units matrix")
    values = np.unique(matrix[~np.isnan(matrix)])
    index = {v: i for i, v in enumerate(values)}
    o = np.zeros((len(values), len(values)))
    for unit in matrix.T:
        present = unit[~np.isnan(unit)]
        m = len(present)
        if m < 2:
            continue
        counts = np.zeros(len(values))
        for v in present:
            counts[index[v]] += 1
        # ordered pairs from different coders: n_c * n_k, minus self-pairs on the diagonal
        o += (np.outer(counts, counts) - np.diag(counts)) / (m - 1)
    keep = o.sum(axis=1) > 0
    return values[keep], o[np.ix_(keep, keep)]


def _delta2(
    values: NDArray[np.float64], marginals: NDArray[np.float64], level: Level
) -> NDArray[np.float64]:
    c, k = np.meshgrid(values, values, indexing="ij")
    if level == "nominal":
        return np.asarray(c != k, dtype=np.float64)
    if level == "interval":
        return np.asarray((c - k) ** 2, dtype=np.float64)
    if level == "ratio":
        total = c + k
        with np.errstate(invalid="ignore", divide="ignore"):
            out = np.where(total == 0, 0.0, ((c - k) / total) ** 2)
        return np.asarray(out, dtype=np.float64)
    if level == "ordinal":
        cumulative = np.cumsum(marginals)
        i, j = np.meshgrid(np.arange(len(values)), np.arange(len(values)), indexing="ij")
        low, high = np.minimum(i, j), np.maximum(i, j)
        # sum of marginals from the lower to the higher rank, minus half of the two ends
        between = cumulative[high] - np.where(low > 0, cumulative[low - 1], 0.0)
        out = (between - (marginals[i] + marginals[j]) / 2) ** 2
        return np.asarray(np.where(i == j, 0.0, out), dtype=np.float64)
    raise ValueError(f"unknown level of measurement: {level}")


def krippendorff_alpha(data: ArrayLike, level: Level = "nominal") -> float:
    """Krippendorff's alpha. ``nan`` when there is no variation to judge agreement on."""
    values, o = coincidences(data)
    marginals = o.sum(axis=1)
    n = marginals.sum()
    if len(values) < 2 or n <= 1:
        return float("nan")
    delta = _delta2(values, marginals, level)
    observed = float((o * delta).sum())
    expected = float((np.outer(marginals, marginals) * delta).sum()) / (n - 1)
    return 1.0 - observed / expected if expected > 0 else float("nan")
