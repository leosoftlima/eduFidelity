"""Human calibration of the composite score (RQ4).

Until the study's ratings exist, this module runs only on SIMULATED raters
(``simulate.py``). Nothing it produces today is a result of the study.
"""

from .data import PREDICTORS_4, PREDICTORS_6, CalibrationData, Rating, from_tables
from .ordinal import OrdinalRidge
from .validation import ablation, bootstrap, fit_calibrated, lodo, standalone

__all__ = [
    "PREDICTORS_4",
    "PREDICTORS_6",
    "CalibrationData",
    "OrdinalRidge",
    "Rating",
    "ablation",
    "bootstrap",
    "fit_calibrated",
    "from_tables",
    "lodo",
    "standalone",
]
