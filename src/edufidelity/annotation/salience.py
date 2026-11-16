"""Salience annotation of reference elements: sheets, majority resolution, frozen labels.

Annotators label every element of a reference as Essential, Supporting or Decorative,
reading the task brief of that page and the guide in ``docs/annotation/``. They never
see generated pages. Labels are resolved by strict majority; an element without a
majority goes to adjudication, which is recorded. The labeled reference is then frozen:
its digest is stored before any measurement (invariant 1).
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from ..models import Reference, Salience
from .agreement import krippendorff_alpha

#: Order used for ordinal agreement: losing an Essential element is the worst case.
SALIENCE_ORDER = {Salience.DECORATIVE: 0, Salience.SUPPORTING: 1, Salience.ESSENTIAL: 2}
SHEET_FIELDS = ["element_id", "type", "text", "x", "y", "w", "h", "salience", "note"]


class TaskBrief(BaseModel):
    """What the learner must do on a page. Written before any generated output exists."""

    interface_id: str
    function: str  # e.g. expository content, assessment, navigation
    objective: str  # what the learner should achieve on this page
    expected_action: str  # what the learner does
    completion_criterion: str  # how one knows the activity is complete

    def to_markdown(self) -> str:
        return "\n".join([
            f"# Task brief · {self.interface_id}", "",
            f"- **Function of the page:** {self.function}",
            f"- **Objective:** {self.objective}",
            f"- **Expected action:** {self.expected_action}",
            f"- **Completion criterion:** {self.completion_criterion}", "",
            "Label each element with the guide in `docs/annotation/salience-guide.md`. "
            "Ask of each one: without it, could the learner still interpret, perform, "
            "navigate or complete this activity?", "",
        ])


class SheetError(ValueError):
    """An annotation sheet is incomplete or does not match its reference."""


def write_sheet(reference: Reference, target: Path) -> None:
    """One row per reference element, salience left blank. Existing labels are omitted."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, lineterminator="\n")
        writer.writeheader()
        for e in reference.elements:
            writer.writerow({
                "element_id": e.id, "type": e.type.value, "text": e.text[:120],
                "x": f"{e.bbox.x:.3f}", "y": f"{e.bbox.y:.3f}",
                "w": f"{e.bbox.w:.3f}", "h": f"{e.bbox.h:.3f}", "salience": "", "note": "",
            })


def read_sheet(path: Path, reference: Reference) -> dict[str, Salience]:
    """Read a filled sheet. Every element must be labeled exactly once."""
    expected = {e.id for e in reference.elements}
    labels: dict[str, Salience] = {}
    seen: set[str] = set()
    problems = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            element, value = row["element_id"], (row.get("salience") or "").strip().lower()
            seen_before = element in seen
            seen.add(element)
            if element not in expected:
                problems.append(f"unknown element {element!r}")
            elif seen_before:
                problems.append(f"element {element!r} labeled twice")
            elif value not in {s.value for s in Salience}:
                problems.append(f"element {element!r}: label {value or '(blank)'!r}")
            else:
                labels[element] = Salience(value)
    missing = expected - seen
    problems += [f"element {m!r} missing" for m in sorted(missing)]
    if problems:
        raise SheetError(f"{path.name}: " + "; ".join(problems))
    return labels


@dataclass
class Resolution:
    labels: dict[str, Salience]  # resolved by majority or adjudication
    adjudication: list[str]  # elements without a strict majority and no decision yet
    adjudicated: dict[str, Salience] = field(default_factory=dict)
    alpha_nominal: float = float("nan")
    alpha_ordinal: float = float("nan")
    n_annotators: int = 0

    @property
    def complete(self) -> bool:
        return not self.adjudication


def resolve(
    reference: Reference,
    sheets: Mapping[str, Mapping[str, Salience]],
    adjudicated: Mapping[str, Salience] | None = None,
) -> Resolution:
    """Strict majority per element; ties and pluralities go to adjudication."""
    if len(sheets) < 2:
        raise ValueError("salience needs at least two annotators")
    adjudicated = dict(adjudicated or {})
    ids = [e.id for e in reference.elements]
    labels: dict[str, Salience] = {}
    pending = []
    for element in ids:
        votes = Counter(sheet[element] for sheet in sheets.values() if element in sheet)
        top, count = votes.most_common(1)[0]
        if element in adjudicated:
            labels[element] = adjudicated[element]
        elif count * 2 > sum(votes.values()):
            labels[element] = top
        else:
            pending.append(element)
    matrix = np.array([[SALIENCE_ORDER[sheet[e]] if e in sheet else np.nan for e in ids]
                       for sheet in sheets.values()], dtype=np.float64)
    return Resolution(
        labels=labels, adjudication=pending,
        adjudicated={k: v for k, v in adjudicated.items() if k in ids},
        alpha_nominal=krippendorff_alpha(matrix, "nominal"),
        alpha_ordinal=krippendorff_alpha(matrix, "ordinal"),
        n_annotators=len(sheets),
    )


def apply_labels(reference: Reference, resolution: Resolution) -> Reference:
    """The labeled reference. Refuses while any element awaits adjudication."""
    if not resolution.complete:
        raise SheetError(f"awaiting adjudication: {', '.join(resolution.adjudication)}")
    elements = [e.model_copy(update={"salience": resolution.labels[e.id]})
                for e in reference.elements]
    return reference.model_copy(update={"elements": elements})


def read_adjudication(path: Path) -> dict[str, Salience]:
    """CSV with element_id,salience,reason. The reason is required and kept in the file."""
    decided = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not (row.get("reason") or "").strip():
                raise SheetError(f"adjudication of {row['element_id']!r} has no reason")
            decided[row["element_id"]] = Salience(row["salience"].strip().lower())
    return decided


def sheets_from_paths(
    paths: Sequence[Path], reference: Reference
) -> dict[str, dict[str, Salience]]:
    """Annotator id is the file name: ``<annotator>.csv``."""
    return {p.stem: read_sheet(p, reference) for p in paths}
