"""Markdown report of a calibration run: LODO by domain, ablation, bootstrap intervals."""

from __future__ import annotations

import csv
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..models import MeasureRow
from .data import PREDICTORS_6, CalibrationData, Rating
from .validation import Ablation, BootstrapResult, ablation, bootstrap, fit_calibrated, standalone


@dataclass
class Section:
    title: str
    note: str
    data: CalibrationData
    result: Ablation
    boot: BootstrapResult | None
    standalone: dict[str, dict[str, float]]
    coefficients: dict[str, float]
    alpha: float


def run_section(
    title: str, note: str, data: CalibrationData, n_resamples: int, seed: int
) -> Section:
    final = fit_calibrated(data, PREDICTORS_6, seed=seed)
    return Section(
        title=title, note=note, data=data, result=ablation(data, seed=seed),
        boot=bootstrap(data, n_resamples, seed=seed) if n_resamples else None,
        standalone=standalone(data),
        coefficients=dict(zip(PREDICTORS_6, final.coef_.tolist(), strict=True)),
        alpha=final.alpha,
    )


def _f(value: float, digits: int = 3) -> str:
    return "–" if value is None or math.isnan(value) else f"{value:.{digits}f}"


def render(sections: Sequence[Section], banner: str) -> str:
    lines = ["# Calibration", "", banner, ""]
    for s in sections:
        r = s.result
        lines += [f"## {s.title}", "", s.note, "",
                  f"{len(s.data.page_ids)} generated pages, {len(set(s.data.interface.tolist()))} "
                  f"reference interfaces, {len(s.data.domains)} domains, "
                  f"{len(s.data.rating_level)} ratings.", "",
                  "### Leave-one-domain-out (6 predictors)", "",
                  "| Held-out domain | Pages | Ridge alpha | Spearman | MAE (1–5) "
                  "| Absent levels |",
                  "|---|---:|---:|---:|---:|---|"]
        for d in r.six.domains:
            absent = ", ".join(str(level + 1) for level in d.absent_levels) or "none"
            lines.append(f"| {d.domain} | {d.n_pages} | {d.alpha:g} | {_f(d.spearman)} | "
                         f"{_f(d.mae)} | {absent} |")
        lines += [f"| **mean** | | | **{_f(r.six.mean_spearman)}** | **{_f(r.six.mean_mae)}** | |",
                  "", "### Ablation: 6 predictors against 4 (without salience)", "",
                  "| | Spearman | MAE (1–5) |", "|---|---:|---:|",
                  f"| 6 predictors | {_f(r.six.mean_spearman)} | {_f(r.six.mean_mae)} |",
                  f"| 4 predictors | {_f(r.four.mean_spearman)} | {_f(r.four.mean_mae)} |",
                  f"| gain from salience | {_f(r.spearman_gain)} | {_f(r.mae_gain)} |"]
        if s.boot is not None:
            sg = s.boot.interval(s.boot.spearman_gain)
            mg = s.boot.interval(s.boot.mae_gain)
            s6 = s.boot.interval(s.boot.spearman_six)
            lines += [f"| 95% interval of the gain ({s.boot.n_resamples} resamples) | "
                      f"{_f(sg[0])} to {_f(sg[1])} | {_f(mg[0])} to {_f(mg[1])} |", "",
                      f"95% interval of the 6-predictor Spearman: {_f(s6[0])} to {_f(s6[1])}. "
                      "Each resample draws reference interfaces with replacement inside every "
                      "domain and reruns the whole procedure, ridge selection included."]
        lines += ["", "### Single measures (Spearman with the mean rating, mean over domains)", "",
                  "| Measure | Spearman |", "|---|---:|"]
        for name, values in s.standalone.items():
            lines.append(f"| {name} | {_f(values['mean'])} |")
        lines += ["", f"### Model fitted on all domains (ridge alpha {s.alpha:g})", "",
                  "Coefficients on standardized predictors; positive means a higher rating.", "",
                  "| Predictor | Coefficient |", "|---|---:|"]
        for name, value in s.coefficients.items():
            lines.append(f"| {name} | {_f(value)} |")
        lines.append("")
    lines += ["## Not done yet", "",
              "- A test of the proportional-odds assumption.",
              "- Ordinal mixed-effects models with rater and interface random effects "
              "(open question Q5; no mature Python implementation).",
              ""]
    return "\n".join(lines)


def read_measures(path: Path) -> list[MeasureRow]:
    """Read a table written by ``edufidelity examples/measure``; empty cells are undefined."""
    rows = []
    with path.open(encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            known = {k: v for k, v in record.items() if k in MeasureRow.model_fields}
            rows.append(MeasureRow.model_validate(
                {k: v for k, v in known.items() if v != ""}))
    return rows


def read_ratings(path: Path) -> list[Rating]:
    with path.open(encoding="utf-8") as handle:
        return [Rating(generated_id=row["generated_id"], rater_id=row["rater_id"],
                       rating=int(row["rating"])) for row in csv.DictReader(handle)]


def write(sections: Sequence[Section], out_dir: Path, banner: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "README.md"
    target.write_text(render(sections, banner), encoding="utf-8")
    with (out_dir / "lodo-predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["section", "predictors", "generated_id", "domain", "predicted", "human"])
        for s in sections:
            for result in (s.result.six, s.result.four):
                for pid, dom, pred, human in zip(result.page_ids, result.page_domain,
                                                 result.predicted, result.human, strict=True):
                    writer.writerow([s.title, len(result.predictors), pid, dom,
                                     f"{pred:.4f}", f"{human:.4f}"])
    if any(s.boot is not None for s in sections):
        with (out_dir / "bootstrap.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["section", "resample", "spearman_6", "spearman_4", "mae_6", "mae_4"])
            for s in sections:
                if s.boot is None:
                    continue
                for i, row in enumerate(np.column_stack([s.boot.spearman_six, s.boot.spearman_four,
                                                         s.boot.mae_six, s.boot.mae_four])):
                    writer.writerow([s.title, i, *(f"{v:.4f}" for v in row)])
    return target
