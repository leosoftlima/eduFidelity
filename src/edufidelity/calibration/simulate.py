"""SIMULATED raters, for rehearsing the calibration procedure. NOT HUMAN DATA.

Generates measurement rows and 1-to-5 ratings with a known generating process, so the
procedure can be checked against the truth: does it recover the signal when the
salience-conditioned measures matter, and does it report a null result when they do
not? Every number derived from this module is a simulation and must be labeled so.

The process, per generated page:

    latent = signal(measures) + domain shift + interface effect
    rating = ordinal cut of (latent + rater leniency + logistic noise)

Domains shift the latent quality, which a model trained on other domains cannot learn;
this is the situation leave-one-domain-out validation exists to expose.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models import MeasureRow
from .data import Rating

DOMAINS = ("biology", "history", "mathematics", "languages")


@dataclass(frozen=True)
class Scenario:
    name: str
    salience_matters: bool
    description: str


SCENARIOS = (
    Scenario("salience-matters", True,
             "raters weigh losing Essential and Supporting elements heavily"),
    Scenario("null", False,
             "raters ignore salience: only the visual and structural measures drive ratings"),
)


def simulate(
    seed: int,
    *,
    salience_matters: bool = True,
    interfaces_per_domain: int = 8,
    pages_per_interface: int = 4,
    n_raters: int = 6,
    raters_per_page: int = 3,
    domains: tuple[str, ...] = DOMAINS,
) -> tuple[list[MeasureRow], list[Rating]]:
    rng = np.random.default_rng(seed)
    leniency = rng.normal(0, 0.3, n_raters)
    rows: list[MeasureRow] = []
    latent: list[float] = []
    for domain in domains:
        domain_shift = rng.normal(0, 0.4)
        for i in range(interfaces_per_domain):
            interface = f"{domain}-{i:02d}"
            interface_effect = rng.normal(0, 0.3)
            for j in range(pages_per_interface):
                ess = 1.0 if rng.random() < 0.55 else rng.uniform(0.25, 1.0)
                sup = 1.0 if rng.random() < 0.5 else rng.uniform(0.2, 1.0)
                dec = 1.0 if rng.random() < 0.4 else rng.uniform(0.0, 1.0)
                layout = float(np.clip(rng.uniform(0.1, 1.0), 0, 1))
                ep_f1 = float(np.clip(0.45 * ess + 0.3 * sup + 0.25 * dec
                                      + rng.normal(0, 0.03), 0, 1))
                ssim = float(np.clip(0.80 + 0.15 * layout + rng.normal(0, 0.03), 0, 1))
                uiclip = float(np.clip(0.95 + 0.04 * rng.random() + rng.normal(0, 0.01), 0, 1))
                if salience_matters:
                    signal = 3.0 * ess + 1.2 * sup + 2.0 * layout + 6.0 * ssim
                else:
                    signal = 2.5 * layout + 8.0 * ssim + 2.0 * ep_f1
                latent.append(signal + domain_shift + interface_effect)
                rows.append(MeasureRow(
                    interface_id=interface, generated_id=f"{interface}--g{j}", domain=domain,
                    ssim=ssim, uiclip=uiclip, ep_f1=ep_f1, layout_fidelity=layout,
                    ped_essential=ess, ped_supporting=sup, ped_decorative=dec,
                ))
    values = np.array(latent)
    cuts = np.quantile(values, [0.12, 0.35, 0.62, 0.85])  # spread ratings over 1..5
    ratings: list[Rating] = []
    for row, value in zip(rows, values, strict=True):
        for rater in rng.choice(n_raters, size=raters_per_page, replace=False):
            noisy = value + leniency[rater] + rng.logistic(0, 0.35)
            ratings.append(Rating(generated_id=row.generated_id, rater_id=f"rater-{rater}",
                                  rating=int(np.searchsorted(cuts, noisy)) + 1))
    return rows, ratings
