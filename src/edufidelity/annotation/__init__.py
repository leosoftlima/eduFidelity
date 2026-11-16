"""Human evaluation kit (RQ1, RQ3): salience annotation, blind rating assignment, agreement.

Guide and templates for the people involved are in ``docs/annotation/``.
"""

from .agreement import krippendorff_alpha
from .assignment import PageToRate, Rater, assign, collect, write_sheets
from .salience import TaskBrief, apply_labels, read_sheet, resolve, write_sheet

__all__ = [
    "PageToRate",
    "Rater",
    "TaskBrief",
    "apply_labels",
    "assign",
    "collect",
    "krippendorff_alpha",
    "read_sheet",
    "resolve",
    "write_sheet",
    "write_sheets",
]
