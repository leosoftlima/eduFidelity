"""Leave-one-domain-out validation, ablation and clustered bootstrap.

Procedure, for one set of predictors:

1. Hold out one domain. Everything below uses the remaining domains only.
2. Choose the ridge strength by grouped cross-validation, with folds made of whole
   reference interfaces, minimizing held-out log-loss.
3. Fit on all training domains with that strength (preprocessing included).
4. Score the held-out pages and compare with the mean human rating of each page:
   Spearman correlation and mean absolute error on the 1-to-5 scale.

The ablation runs the same procedure with 4 and 6 predictors and takes the paired
difference. The bootstrap resamples reference interfaces within each domain and reruns
the whole procedure, calibration included, on every resample.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr

from .data import PREDICTORS_4, PREDICTORS_6, CalibrationData
from .ordinal import OrdinalRidge

ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)


def spearman(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def grouped_folds(groups: NDArray[np.str_], n_folds: int, seed: int) -> list[NDArray[np.bool_]]:
    """Validation masks; every group falls entirely in one fold."""
    unique = np.array(sorted(set(groups.tolist())))
    np.random.default_rng(seed).shuffle(unique)
    k = min(n_folds, len(unique))
    return [np.isin(groups, chunk) for chunk in np.array_split(unique, k)]


def select_alpha(
    data: CalibrationData, predictors: Sequence[str], alphas: Sequence[float] = ALPHAS,
    n_folds: int = 5, seed: int = 0,
) -> float:
    losses = []
    for alpha in alphas:
        fold_losses = []
        for valid in grouped_folds(data.interface, n_folds, seed):
            train, test = data.subset(~valid), data.subset(valid)
            if len(test.rating_level) == 0 or len(train.rating_level) == 0:
                continue
            model = OrdinalRidge(n_levels=data.n_levels, alpha=alpha)
            model.fit(*train.ratings_matrix(predictors))
            fold_losses.append(model.log_loss(*test.ratings_matrix(predictors)))
        losses.append(np.mean(fold_losses))
    return float(alphas[int(np.argmin(losses))])


def fit_calibrated(
    data: CalibrationData, predictors: Sequence[str], alphas: Sequence[float] = ALPHAS,
    seed: int = 0,
) -> OrdinalRidge:
    alpha = select_alpha(data, predictors, alphas, seed=seed)
    return OrdinalRidge(n_levels=data.n_levels, alpha=alpha).fit(
        *data.ratings_matrix(predictors))


@dataclass
class DomainResult:
    domain: str
    alpha: float
    spearman: float
    mae: float
    n_pages: int
    absent_levels: list[int]
    model: OrdinalRidge


@dataclass
class LodoResult:
    predictors: tuple[str, ...]
    domains: list[DomainResult]
    page_ids: NDArray[np.str_]
    predicted: NDArray[np.float64]  # expected rating, 1 .. K
    human: NDArray[np.float64]  # mean human rating, 1 .. K
    page_domain: NDArray[np.str_] = field(default_factory=lambda: np.array([], dtype=np.str_))

    @property
    def mean_spearman(self) -> float:
        return float(np.nanmean([d.spearman for d in self.domains]))

    @property
    def mean_mae(self) -> float:
        return float(np.mean([d.mae for d in self.domains]))


def lodo(
    data: CalibrationData, predictors: Sequence[str] = PREDICTORS_6,
    alphas: Sequence[float] = ALPHAS, seed: int = 0,
) -> LodoResult:
    results, ids, predicted, human, page_domain = [], [], [], [], []
    for domain in data.domains:
        held = data.domain == domain
        train, test = data.subset(~held), data.subset(held)
        model = fit_calibrated(train, predictors, alphas, seed)
        pred = 1.0 + model.expected_level(test.pages_matrix(predictors))
        truth = test.human_mean()
        rated = ~np.isnan(truth)
        results.append(DomainResult(
            domain=domain, alpha=model.alpha,
            spearman=spearman(pred[rated], truth[rated]),
            mae=float(np.mean(np.abs(pred[rated] - truth[rated]))),
            n_pages=int(rated.sum()), absent_levels=model.absent_levels_, model=model,
        ))
        ids.append(test.page_ids[rated])
        predicted.append(pred[rated])
        human.append(truth[rated])
        page_domain.append(test.domain[rated])
    return LodoResult(tuple(predictors), results, np.concatenate(ids),
                      np.concatenate(predicted), np.concatenate(human),
                      np.concatenate(page_domain))


def standalone(data: CalibrationData) -> dict[str, dict[str, float]]:
    """Spearman of each single measure with the mean human rating, by domain."""
    truth = data.human_mean()
    out: dict[str, dict[str, float]] = {}
    for name, values in data.features.items():
        out[name] = {}
        for domain in data.domains:
            mask = (data.domain == domain) & ~np.isnan(truth) & ~np.isnan(values)
            out[name][domain] = spearman(values[mask], truth[mask])
        out[name]["mean"] = float(np.nanmean(list(out[name].values())))
    return out


@dataclass
class Ablation:
    six: LodoResult
    four: LodoResult

    @property
    def spearman_gain(self) -> float:
        return self.six.mean_spearman - self.four.mean_spearman

    @property
    def mae_gain(self) -> float:
        """Positive when 6 predictors make smaller errors."""
        return self.four.mean_mae - self.six.mean_mae


def ablation(data: CalibrationData, alphas: Sequence[float] = ALPHAS, seed: int = 0) -> Ablation:
    return Ablation(six=lodo(data, PREDICTORS_6, alphas, seed),
                    four=lodo(data, PREDICTORS_4, alphas, seed))


@dataclass
class BootstrapResult:
    n_resamples: int
    spearman_six: NDArray[np.float64]
    spearman_four: NDArray[np.float64]
    mae_six: NDArray[np.float64]
    mae_four: NDArray[np.float64]

    @staticmethod
    def interval(values: NDArray[np.float64], level: float = 0.95) -> tuple[float, float]:
        tail = (1 - level) / 2 * 100
        low, high = np.nanpercentile(values, [tail, 100 - tail])
        return float(low), float(high)

    @property
    def spearman_gain(self) -> NDArray[np.float64]:
        return np.asarray(self.spearman_six - self.spearman_four, dtype=np.float64)

    @property
    def mae_gain(self) -> NDArray[np.float64]:
        return np.asarray(self.mae_four - self.mae_six, dtype=np.float64)


def bootstrap(
    data: CalibrationData, n_resamples: int = 200, seed: int = 0,
    alphas: Sequence[float] = ALPHAS,
) -> BootstrapResult:
    """Resample interfaces within each domain; rerun calibration and LODO each time."""
    rng = np.random.default_rng(seed)
    by_domain = {d: sorted(set(data.interface[data.domain == d].tolist())) for d in data.domains}
    s6, s4, m6, m4 = [], [], [], []
    for b in range(n_resamples):
        picks = [str(name) for d in data.domains
                 for name in rng.choice(by_domain[d], size=len(by_domain[d]), replace=True)]
        sample = data.take_interfaces(picks)
        result = ablation(sample, alphas, seed=seed + b)
        s6.append(result.six.mean_spearman)
        s4.append(result.four.mean_spearman)
        m6.append(result.six.mean_mae)
        m4.append(result.four.mean_mae)
    return BootstrapResult(n_resamples, np.array(s6), np.array(s4), np.array(m6), np.array(m4))
