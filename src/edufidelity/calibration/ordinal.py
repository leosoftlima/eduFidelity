"""Proportional-odds ordinal logistic regression with an L2 (ridge) penalty.

    P(Y <= k | x) = sigmoid(theta_k - x . beta),   k = 0 .. K-2

Levels are 0-indexed internally (a 1-to-5 rating is 0 to 4). Thresholds are kept
ordered by construction: theta_0 = c and theta_k = theta_(k-1) + exp(d_k).

Objective: the summed negative log-likelihood, plus ``alpha / 2 * ||beta||^2`` on the
coefficients of standardized predictors, plus a weak ``tau / 2 * (c^2 + sum d_k^2)``
on the thresholds. The weak term keeps thresholds finite when a level is absent from
the training data (open question Q6); levels absent from a fit are recorded on the
model, never hidden. Optimized with L-BFGS-B and the analytic gradient.

Preprocessing (missing-value imputation and standardization) is part of the model and
is fitted on the training data only, so cross-validation cannot leak (invariant 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import expit

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass
class Preprocessor:
    """Mean imputation and standardization, both learned from the training rows."""

    mean_: FloatArray = field(default_factory=lambda: np.zeros(0))
    scale_: FloatArray = field(default_factory=lambda: np.ones(0))

    def fit(self, x: FloatArray) -> Preprocessor:
        mean = np.nanmean(x, axis=0)
        mean = np.where(np.isnan(mean), 0.0, mean)  # a column missing everywhere
        filled = np.where(np.isnan(x), mean, x)
        scale = filled.std(axis=0)
        self.mean_, self.scale_ = mean, np.where(scale > 0, scale, 1.0)
        return self

    def transform(self, x: FloatArray) -> FloatArray:
        filled = np.where(np.isnan(x), self.mean_, x)
        return np.asarray((filled - self.mean_) / self.scale_, dtype=np.float64)


def thresholds_from(params: FloatArray, n_levels: int) -> FloatArray:
    c, d = params[0], params[1 : n_levels - 1]
    return np.asarray(np.concatenate([[c], c + np.cumsum(np.exp(d))]), dtype=np.float64)


def _objective(
    params: FloatArray, x: FloatArray, y: IntArray, n_levels: int, alpha: float, tau: float
) -> tuple[float, FloatArray]:
    n_thr = n_levels - 1
    theta = thresholds_from(params, n_levels)
    beta = params[n_thr:]
    eta = x @ beta
    upper = np.where(y < n_thr, theta[np.minimum(y, n_thr - 1)] - eta, np.inf)
    lower = np.where(y > 0, theta[np.maximum(y - 1, 0)] - eta, -np.inf)
    s_up, s_lo = expit(upper), expit(lower)
    prob = np.clip(s_up - s_lo, 1e-300, None)
    # derivative of sigmoid; zero at +-inf
    g_up = np.where(np.isfinite(upper), s_up * (1 - s_up), 0.0)
    g_lo = np.where(np.isfinite(lower), s_lo * (1 - s_lo), 0.0)

    loss = -np.sum(np.log(prob)) + 0.5 * alpha * beta @ beta
    loss += 0.5 * tau * (params[0] ** 2 + params[1:n_thr] @ params[1:n_thr])

    # gradient with respect to the thresholds, then chained to (c, d)
    grad_theta = np.zeros(n_thr)
    np.add.at(grad_theta, np.minimum(y, n_thr - 1)[y < n_thr], -(g_up / prob)[y < n_thr])
    np.add.at(grad_theta, np.maximum(y - 1, 0)[y > 0], (g_lo / prob)[y > 0])
    grad = np.zeros_like(params)
    grad[0] = grad_theta.sum() + tau * params[0]
    increments = np.exp(params[1:n_thr])
    # theta_k depends on d_j for every j <= k
    tail = np.cumsum(grad_theta[::-1])[::-1]  # sum over k >= j
    grad[1:n_thr] = increments * tail[1:] + tau * params[1:n_thr]
    grad[n_thr:] = x.T @ ((g_up - g_lo) / prob) + alpha * beta
    return float(loss), grad


@dataclass
class OrdinalRidge:
    """Ordinal ridge regression with built-in, training-only preprocessing."""

    n_levels: int = 5
    alpha: float = 1.0
    tau: float = 1e-3
    preprocess: bool = True
    coef_: FloatArray = field(default_factory=lambda: np.zeros(0))
    thresholds_: FloatArray = field(default_factory=lambda: np.zeros(0))
    absent_levels_: list[int] = field(default_factory=list)
    converged_: bool = False
    _prep: Preprocessor = field(default_factory=Preprocessor)

    def fit(self, x: FloatArray, y: IntArray) -> OrdinalRidge:
        y = np.asarray(y, dtype=np.int64)
        if int(np.min(y)) < 0 or int(np.max(y)) >= self.n_levels:
            raise ValueError(f"levels must be in 0..{self.n_levels - 1}")
        self.absent_levels_ = sorted(set(range(self.n_levels)) - set(y.tolist()))
        z = self._prep.fit(x).transform(x) if self.preprocess else np.asarray(x, np.float64)
        # start from the marginal cumulative logits, beta = 0
        counts = np.bincount(y, minlength=self.n_levels) + 0.5
        cumulative = np.cumsum(counts)[:-1] / counts.sum()
        theta0 = np.log(cumulative / (1 - cumulative))
        start = np.concatenate(
            [[theta0[0]], np.log(np.maximum(np.diff(theta0), 1e-3)), np.zeros(z.shape[1])]
        )
        result = minimize(
            _objective, start, args=(z, y, self.n_levels, self.alpha, self.tau),
            jac=True, method="L-BFGS-B",
            options={"maxiter": 5000, "gtol": 1e-8, "ftol": 1e-13},
        )
        self.converged_ = bool(result.success)
        n_thr = self.n_levels - 1
        self.thresholds_ = thresholds_from(result.x, self.n_levels)
        self.coef_ = np.asarray(result.x[n_thr:], dtype=np.float64)
        return self

    def predict_proba(self, x: FloatArray) -> FloatArray:
        z = self._prep.transform(x) if self.preprocess else np.asarray(x, np.float64)
        cumulative = expit(self.thresholds_[None, :] - (z @ self.coef_)[:, None])
        padded = np.hstack([np.zeros((len(z), 1)), cumulative, np.ones((len(z), 1))])
        return np.asarray(np.diff(padded, axis=1), dtype=np.float64)

    def expected_level(self, x: FloatArray) -> FloatArray:
        """Expected rating on the 0 .. K-1 scale."""
        return np.asarray(self.predict_proba(x) @ np.arange(self.n_levels), dtype=np.float64)

    def score(self, x: FloatArray) -> FloatArray:
        """The composite EduFidelity score: expected rating rescaled to 0 .. 1."""
        return self.expected_level(x) / (self.n_levels - 1)

    def log_loss(self, x: FloatArray, y: IntArray) -> float:
        prob = self.predict_proba(x)[np.arange(len(y)), np.asarray(y, dtype=np.int64)]
        return float(-np.mean(np.log(np.clip(prob, 1e-300, None))))
