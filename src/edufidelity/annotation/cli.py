"""Command-line part of the human evaluation kit. Registered by ``edufidelity.cli``."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ..models import Reference
from .agreement import krippendorff_alpha
from .assignment import PageToRate, Rater, assign, collect, rating_matrix, write_sheets
from .salience import (
    TaskBrief,
    apply_labels,
    read_adjudication,
    resolve,
    sheets_from_paths,
    write_sheet,
)

COMMANDS = (
    "annotation-sheets",
    "resolve-salience",
    "assign-ratings",
    "collect-ratings",
    "agreement",
)


def register(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sheets = commands.add_parser(
        "annotation-sheets", help="blank salience sheets and the brief for annotators"
    )
    sheets.add_argument("reference", type=Path, help="reference JSON")
    sheets.add_argument("--brief", type=Path, required=True, help="task brief JSON")
    sheets.add_argument("--annotators", required=True, help="comma-separated ids")
    sheets.add_argument("--out", type=Path, default=Path("annotation"))

    res = commands.add_parser(
        "resolve-salience", help="majority labels, adjudication list and agreement"
    )
    res.add_argument("reference", type=Path)
    res.add_argument("sheets", type=Path, nargs="+", help="filled sheets: <annotator>.csv")
    res.add_argument(
        "--adjudication", type=Path, default=None, help="CSV element_id,salience,reason"
    )
    res.add_argument("--out", type=Path, required=True, help="labeled reference JSON")

    asg = commands.add_parser("assign-ratings", help="blind rating sheets, balanced by group")
    asg.add_argument("measures", type=Path, help="CSV of measurement rows (pages to rate)")
    asg.add_argument("raters", type=Path, help="CSV: rater_id,group")
    asg.add_argument(
        "--annotators",
        type=Path,
        default=None,
        help="CSV: interface_id,annotator_id (excluded from rating those pages)",
    )
    asg.add_argument("--per-group", type=int, default=1)
    asg.add_argument("--seed", type=int, default=7)
    asg.add_argument("--out", type=Path, default=Path("rating"))

    col = commands.add_parser("collect-ratings", help="read filled rating sheets via the key")
    col.add_argument("folder", type=Path, help="folder written by assign-ratings")
    col.add_argument("--out", type=Path, required=True, help="ratings CSV")

    agr = commands.add_parser("agreement", help="Krippendorff's alpha between raters")
    agr.add_argument("ratings", type=Path, help="CSV: generated_id,rater_id,rating")
    agr.add_argument(
        "--level", default="ordinal", choices=["nominal", "ordinal", "interval", "ratio"]
    )


def run(args: argparse.Namespace) -> int:
    if args.command == "annotation-sheets":
        reference = Reference.model_validate_json(args.reference.read_text("utf-8"))
        brief = TaskBrief.model_validate_json(args.brief.read_text("utf-8"))
        if brief.interface_id != reference.interface_id:
            raise SystemExit("the brief belongs to another interface")
        folder = args.out / reference.interface_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "brief.md").write_text(brief.to_markdown(), encoding="utf-8")
        for annotator in args.annotators.split(","):
            write_sheet(reference, folder / f"{annotator.strip()}.csv")
        print(folder)
        return 0

    if args.command == "resolve-salience":
        reference = Reference.model_validate_json(args.reference.read_text("utf-8"))
        decided = read_adjudication(args.adjudication) if args.adjudication else None
        resolution = resolve(reference, sheets_from_paths(args.sheets, reference), decided)
        print(
            f"annotators: {resolution.n_annotators}  "
            f"alpha nominal: {resolution.alpha_nominal:.3f}  "
            f"alpha ordinal: {resolution.alpha_ordinal:.3f}"
        )
        if not resolution.complete:
            pending = args.out.with_name(args.out.stem + ".adjudication-needed.csv")
            with pending.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(["element_id", "salience", "reason"])
                writer.writerows([e, "", ""] for e in resolution.adjudication)
            print(f"{len(resolution.adjudication)} element(s) need adjudication: {pending}")
            return 2
        labeled = apply_labels(reference, resolution)
        args.out.write_text(labeled.model_dump_json(indent=2), encoding="utf-8")
        print(f"{args.out}  digest {labeled.digest()}")
        return 0

    if args.command == "assign-ratings":
        with args.measures.open(encoding="utf-8") as handle:
            pages = [
                PageToRate(
                    generated_id=r["generated_id"],
                    interface_id=r["interface_id"],
                    domain=r.get("domain") or "",
                )
                for r in csv.DictReader(handle)
                if (r.get("status") or "ok") == "ok"
            ]
        with args.raters.open(encoding="utf-8") as handle:
            raters = [
                Rater(rater_id=r["rater_id"], group=r["group"]) for r in csv.DictReader(handle)
            ]
        annotators: dict[str, set[str]] = {}
        if args.annotators:
            with args.annotators.open(encoding="utf-8") as handle:
                for r in csv.DictReader(handle):
                    annotators.setdefault(r["interface_id"], set()).add(r["annotator_id"])
        assignments = assign(pages, raters, annotators, per_group=args.per_group, seed=args.seed)
        key = write_sheets(assignments, args.out)
        settings = {
            "seed": args.seed,
            "per_group": args.per_group,
            "pages": len(pages),
            "raters": len(raters),
            "assignments": len(assignments),
        }
        (args.out / "assignment.json").write_text(json.dumps(settings, indent=2), "utf-8")
        print(
            f"{len(assignments)} ratings over {len(pages)} pages; give raters only "
            f"{args.out / 'sheets'}, keep {key} with the coordinator"
        )
        return 0

    if args.command == "collect-ratings":
        collected = collect(args.folder)
        with args.out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["generated_id", "rater_id", "rating"])
            writer.writerows([r.generated_id, r.rater_id, r.rating] for r in collected.ratings)
        print(f"{len(collected.ratings)} ratings; {len(collected.missing)} blank")
        for rater, code in collected.missing:
            print(f"  blank: {rater} {code}")
        return 0

    if args.command == "agreement":
        from ..calibration.report import read_ratings

        rater_ids, page_ids, matrix = rating_matrix(read_ratings(args.ratings))
        alpha = krippendorff_alpha(matrix, args.level)
        print(
            f"Krippendorff's alpha ({args.level}): {alpha:.3f} "
            f"({len(rater_ids)} raters, {len(page_ids)} pages)"
        )
        return 0
    raise SystemExit(f"unknown command {args.command}")
