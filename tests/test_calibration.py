"""Calibration: the ordinal model against references, and the validation procedure on
SIMULATED raters. No browser needed."""

from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import check_grad

from edufidelity.calibration import (
    PREDICTORS_4,
    PREDICTORS_6,
    OrdinalRidge,
    Rating,
    ablation,
    bootstrap,
    from_tables,
    lodo,
)
from edufidelity.calibration.data import CalibrationData
from edufidelity.calibration.ordinal import Preprocessor, _objective
from edufidelity.calibration.simulate import simulate
from edufidelity.calibration.validation import grouped_folds
from edufidelity.models import MeasureRow


def ordinal_sample(n: int = 500, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 3))
    latent = x @ np.array([1.0, -0.5, 0.0]) + rng.logistic(size=n)
    return x, np.digitize(latent, [-2.0, -0.7, 0.6, 1.9]).astype(np.int64)


@pytest.fixture(scope="module")
def salience_data() -> CalibrationData:
    return from_tables(*simulate(7, salience_matters=True))


@pytest.fixture(scope="module")
def null_data() -> CalibrationData:
    return from_tables(*simulate(7, salience_matters=False))


# ------------------------------------------------------------------ the ordinal model


def test_analytic_gradient_matches_numerical() -> None:
    x, y = ordinal_sample()
    params = np.random.default_rng(1).normal(size=4 + 3) * 0.3

    def loss(p: np.ndarray) -> float:
        return _objective(p, x, y, 5, 0.7, 0.01)[0]

    def grad(p: np.ndarray) -> np.ndarray:
        return _objective(p, x, y, 5, 0.7, 0.01)[1]

    assert check_grad(loss, grad, params) < 1e-3


def test_unpenalized_fit_matches_statsmodels() -> None:
    from statsmodels.miscmodels.ordinal_model import OrderedModel

    x, y = ordinal_sample()
    ours = OrdinalRidge(alpha=0.0, tau=0.0, preprocess=False).fit(x, y)
    ref = OrderedModel(y, x, distr="logit").fit(method="bfgs", disp=False, maxiter=5000)
    assert ours.converged_
    np.testing.assert_allclose(ours.coef_, ref.params[:3], atol=1e-3)
    thresholds = ref.model.transform_threshold_params(ref.params)[1:-1]
    np.testing.assert_allclose(ours.thresholds_, thresholds, atol=1e-3)


def test_strong_penalty_gives_the_marginal_distribution() -> None:
    """With beta forced to 0, thresholds are the cumulative logits of the level shares."""
    x, y = ordinal_sample()
    model = OrdinalRidge(alpha=1e9, tau=0.0).fit(x, y)
    shares = np.cumsum(np.bincount(y, minlength=5))[:-1] / len(y)
    np.testing.assert_allclose(model.coef_, 0.0, atol=1e-5)
    np.testing.assert_allclose(model.thresholds_, np.log(shares / (1 - shares)), atol=1e-4)


def test_penalty_shrinks_coefficients() -> None:
    x, y = ordinal_sample()
    norms = [np.linalg.norm(OrdinalRidge(alpha=a).fit(x, y).coef_) for a in (0.0, 10.0, 1000.0)]
    assert norms[0] > norms[1] > norms[2]


def test_predictions_are_proper_distributions() -> None:
    x, y = ordinal_sample()
    model = OrdinalRidge().fit(x, y)
    prob = model.predict_proba(x)
    assert np.all(prob >= 0)
    np.testing.assert_allclose(prob.sum(axis=1), 1.0)
    assert np.all(np.diff(model.thresholds_) > 0)
    assert np.all((model.score(x) >= 0) & (model.score(x) <= 1))


def test_absent_level_is_recorded_and_fit_stays_finite() -> None:
    x, y = ordinal_sample()
    keep = y != 4
    model = OrdinalRidge().fit(x[keep], y[keep])
    assert model.absent_levels_ == [4]
    assert np.all(np.isfinite(model.thresholds_)) and np.all(np.isfinite(model.coef_))


def test_preprocessing_uses_training_statistics_only() -> None:
    train = np.array([[1.0, np.nan], [3.0, 4.0], [5.0, 8.0]])
    prep = Preprocessor().fit(train)
    out = prep.transform(np.array([[np.nan, np.nan]]))
    np.testing.assert_allclose(out, 0.0)  # imputed with the training mean, then centered
    assert prep.mean_[1] == pytest.approx(6.0)


# ------------------------------------------------------------------ validation procedure


def test_folds_never_split_an_interface(salience_data: CalibrationData) -> None:
    folds = grouped_folds(salience_data.interface, 5, seed=3)
    for name in set(salience_data.interface.tolist()):
        hits = [bool(np.any(mask & (salience_data.interface == name))) for mask in folds]
        assert sum(hits) == 1
    assert np.all(np.sum(folds, axis=0) == 1)


def test_held_out_domain_does_not_leak_into_its_model(salience_data: CalibrationData) -> None:
    """Invariant 4: changing the held-out domain must not change the model scoring it."""
    first = lodo(salience_data)
    altered_features = {k: v.copy() for k, v in salience_data.features.items()}
    held = salience_data.domain == "biology"
    for values in altered_features.values():
        values[held] = values[held] * 100 + 7
    altered = CalibrationData(
        salience_data.page_ids,
        salience_data.interface,
        salience_data.domain,
        altered_features,
        salience_data.rating_page,
        salience_data.rating_level,
    )
    second = lodo(altered)
    a = next(d for d in first.domains if d.domain == "biology").model
    b = next(d for d in second.domains if d.domain == "biology").model
    assert a.alpha == b.alpha
    np.testing.assert_array_equal(a.coef_, b.coef_)
    np.testing.assert_array_equal(a._prep.mean_, b._prep.mean_)


def test_lodo_covers_every_domain_once(salience_data: CalibrationData) -> None:
    result = lodo(salience_data, PREDICTORS_6)
    assert [d.domain for d in result.domains] == salience_data.domains
    assert len(result.page_ids) == len(set(result.page_ids.tolist())) == len(salience_data.page_ids)


def test_ablation_finds_the_salience_signal_when_it_exists(
    salience_data: CalibrationData,
) -> None:
    result = ablation(salience_data)
    assert result.spearman_gain > 0.02
    assert result.mae_gain > 0


def test_ablation_reports_no_gain_when_there_is_none(null_data: CalibrationData) -> None:
    assert abs(ablation(null_data).spearman_gain) < 0.02


def test_bootstrap_reruns_the_whole_procedure(salience_data: CalibrationData) -> None:
    result = bootstrap(salience_data, n_resamples=3, seed=2)
    assert len(result.spearman_six) == len(result.spearman_four) == 3
    low, high = result.interval(result.spearman_gain)
    assert low <= high


def test_resampled_interfaces_become_distinct_clusters(salience_data: CalibrationData) -> None:
    name = str(salience_data.interface[0])
    sample = salience_data.take_interfaces([name, name])
    assert len(set(sample.interface.tolist())) == 2
    assert len(sample.rating_level) == 2 * int(
        np.sum(salience_data.interface[salience_data.rating_page] == name)
    )


# ------------------------------------------------------------------ data contracts


def test_simulation_is_deterministic() -> None:
    a_rows, a_ratings = simulate(11)
    b_rows, b_ratings = simulate(11)
    assert a_rows == b_rows and a_ratings == b_ratings


def test_ratings_of_unknown_pages_are_rejected() -> None:
    rows = [MeasureRow(interface_id="i", generated_id="p", domain="d", ssim=0.9)]
    with pytest.raises(ValueError, match="without measurements"):
        from_tables(rows, [Rating(generated_id="other", rater_id="r", rating=3)])


def test_failed_renders_are_not_calibrated() -> None:
    rows = [
        MeasureRow(interface_id="i", generated_id="p", domain="d", ssim=0.9),
        MeasureRow(
            interface_id="i", generated_id="q", domain="d", status="render_failure: timeout"
        ),
    ]
    data = from_tables(rows, [Rating(generated_id="p", rater_id="r", rating=3)])
    assert data.page_ids.tolist() == ["p"]


def test_undefined_measures_become_missing_not_zero() -> None:
    rows = [MeasureRow(interface_id="i", generated_id="p", domain="d", ped_supporting=None)]
    data = from_tables(rows, [Rating(generated_id="p", rater_id="r", rating=2)])
    assert np.isnan(data.features["ped_supporting"][0])
    assert set(PREDICTORS_4) < set(PREDICTORS_6)


def test_cli_calibrates_from_csv_files(tmp_path: Path) -> None:
    import csv

    from edufidelity.cli import main, write_table

    rows, ratings = simulate(5, interfaces_per_domain=4, pages_per_interface=3)
    write_table(rows, tmp_path / "measures.csv")
    with (tmp_path / "ratings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["generated_id", "rater_id", "rating"])
        writer.writerows([r.generated_id, r.rater_id, r.rating] for r in ratings)
    out = tmp_path / "report"
    code = main(
        [
            "calibrate",
            str(tmp_path / "measures.csv"),
            str(tmp_path / "ratings.csv"),
            "--resamples",
            "0",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    text = (out / "README.md").read_text("utf-8")
    assert "Leave-one-domain-out" in text and "Ablation" in text
    assert (out / "lodo-predictions.csv").exists()
