"""Blind assignment of generated pages to raters, and collection of their ratings.

Rules, all enforced here:

* Every page is rated by ``per_group`` raters from **each** rater group (for example
  education, design and computing), so every perspective judges every page.
* A rater never judges a page whose reference they annotated for salience.
* Raters see opaque codes, never the generated id, the model or the condition. The key
  that maps codes back is written to a separate file kept by the coordinator.
* Load is balanced: the least-loaded eligible rater is chosen first; ties are broken by
  the seed, and each rater's order of pages is shuffled by the seed.
* Same input and seed give the same assignment (invariant 5).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from ..calibration.data import Rating


class Rater(BaseModel):
    rater_id: str
    group: str


class PageToRate(BaseModel):
    generated_id: str
    interface_id: str
    domain: str = ""


@dataclass(frozen=True)
class Assignment:
    rater_id: str
    code: str
    generated_id: str
    position: int  # order of the page in the rater's sheet


class AssignmentError(ValueError):
    """The constraints cannot be satisfied with the raters available."""


def assign(
    pages: Sequence[PageToRate],
    raters: Sequence[Rater],
    annotators_of: Mapping[str, set[str]] | None = None,
    *,
    per_group: int = 1,
    seed: int = 0,
) -> list[Assignment]:
    annotators_of = annotators_of or {}
    rng = np.random.default_rng(seed)
    groups: dict[str, list[str]] = defaultdict(list)
    for person in raters:
        groups[person.group].append(person.rater_id)
    if len({r.rater_id for r in raters}) != len(raters):
        raise AssignmentError("duplicated rater_id")
    load = {r.rater_id: 0 for r in raters}
    tiebreak = {r.rater_id: float(rng.random()) for r in raters}

    order = rng.permutation(len(pages))
    chosen: dict[str, list[str]] = defaultdict(list)
    for index in order:
        page = pages[int(index)]
        excluded = annotators_of.get(page.interface_id, set())
        for group in sorted(groups):
            eligible = [r for r in groups[group] if r not in excluded]
            if len(eligible) < per_group:
                raise AssignmentError(
                    f"{page.generated_id}: group {group!r} has {len(eligible)} eligible "
                    f"raters, {per_group} needed (annotators of {page.interface_id} excluded)"
                )
            for rater in sorted(eligible, key=lambda r: (load[r], tiebreak[r]))[:per_group]:
                chosen[rater].append(page.generated_id)
                load[rater] += 1

    codes = _opaque_codes(len(pages), rng)
    code_of = {page.generated_id: codes[i] for i, page in enumerate(pages)}
    assignments = []
    for rater in sorted(chosen):
        sheet = [chosen[rater][int(i)] for i in rng.permutation(len(chosen[rater]))]
        assignments += [
            Assignment(rater, code_of[g], g, position) for position, g in enumerate(sheet, start=1)
        ]
    return assignments


def _opaque_codes(n: int, rng: np.random.Generator) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < n:
        code = "P-" + "".join(rng.choice(list("ABCDEFGHJKLMNPQRSTUVWXYZ23456789"), size=6))
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


SHEET_FIELDS = ["position", "code", "rating", "comment"]


def write_sheets(assignments: Sequence[Assignment], out_dir: Path) -> Path:
    """``sheets/<rater>.csv`` for the raters; ``key.csv`` for the coordinator only."""
    sheets = out_dir / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    by_rater: dict[str, list[Assignment]] = defaultdict(list)
    for a in assignments:
        by_rater[a.rater_id].append(a)
    for rater, items in by_rater.items():
        with (sheets / f"{rater}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, lineterminator="\n")
            writer.writeheader()
            for a in sorted(items, key=lambda a: a.position):
                writer.writerow(
                    {"position": a.position, "code": a.code, "rating": "", "comment": ""}
                )
    key = out_dir / "key.csv"
    with key.open("w", newline="", encoding="utf-8") as handle:
        key_writer = csv.writer(handle, lineterminator="\n")
        key_writer.writerow(["code", "generated_id"])
        for code, generated in sorted({(a.code, a.generated_id) for a in assignments}):
            key_writer.writerow([code, generated])
    return key


@dataclass
class Collected:
    ratings: list[Rating]
    missing: list[tuple[str, str]]  # (rater, code) left blank


def collect(out_dir: Path, n_levels: int = 5) -> Collected:
    """Read the filled sheets back through the key. Blank cells are reported, not guessed."""
    key: dict[str, str] = {}
    with (out_dir / "key.csv").open(encoding="utf-8") as handle:
        key = {row["code"]: row["generated_id"] for row in csv.DictReader(handle)}
    ratings, missing = [], []
    for sheet in sorted((out_dir / "sheets").glob("*.csv")):
        with sheet.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                code, value = row["code"], (row.get("rating") or "").strip()
                if code not in key:
                    raise ValueError(f"{sheet.name}: unknown code {code!r}")
                if not value:
                    missing.append((sheet.stem, code))
                    continue
                rating = int(value)
                if not 1 <= rating <= n_levels:
                    raise ValueError(f"{sheet.name}: rating {rating} outside 1..{n_levels}")
                ratings.append(Rating(generated_id=key[code], rater_id=sheet.stem, rating=rating))
    return Collected(ratings, missing)


def rating_matrix(ratings: Sequence[Rating]) -> tuple[list[str], list[str], np.ndarray]:
    """Raters x pages matrix with NaN where a rater did not rate a page."""
    raters = sorted({r.rater_id for r in ratings})
    pages = sorted({r.generated_id for r in ratings})
    matrix = np.full((len(raters), len(pages)), np.nan)
    ri, pi = {r: i for i, r in enumerate(raters)}, {p: i for i, p in enumerate(pages)}
    for r in ratings:
        matrix[ri[r.rater_id], pi[r.generated_id]] = r.rating
    return raters, pages, matrix
