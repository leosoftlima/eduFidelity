"""Command line: ``edufidelity examples`` and ``edufidelity measure``."""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from pathlib import Path

from .examples import run_examples
from .measures import UIClipScorer
from .models import MeasureRow, Reference
from .pipeline import measure
from .render import Renderer


def write_table(rows: Sequence[MeasureRow], target: Path | None) -> None:
    fields = list(MeasureRow.model_fields)
    handle = target.open("w", newline="", encoding="utf-8") if target else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            data = row.model_dump()
            writer.writerow(
                {k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in data.items()}
            )
    finally:
        if target:
            handle.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edufidelity", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    examples = commands.add_parser("examples", help="measure the synthetic examples")
    examples.add_argument("--pages", type=Path, default=Path("examples/pages"))
    examples.add_argument("--build", type=Path, default=Path("examples/_build"))
    examples.add_argument("--out", type=Path, default=None, help="CSV file (default: stdout)")
    examples.add_argument("--uiclip", action="store_true", help="also compute UIClip (extra)")

    study = commands.add_parser("perturbations", help="run the perturbation study")
    study.add_argument("--pages", type=Path, default=Path("examples/pages"))
    study.add_argument("--build", type=Path, default=Path("examples/_build/perturbations"))
    study.add_argument("--out", type=Path, default=Path("supplementary/perturbations"))
    study.add_argument("--no-uiclip", action="store_true", help="skip UIClip (no extra needed)")

    single = commands.add_parser("measure", help="measure one generated page")
    single.add_argument("reference", type=Path, help="reference JSON")
    single.add_argument("reference_png", type=Path)
    single.add_argument("generated", type=Path, help="generated HTML file")
    single.add_argument("--workdir", type=Path, default=Path("_work"))
    single.add_argument("--out", type=Path, default=None)
    single.add_argument("--uiclip", action="store_true", help="also compute UIClip (extra)")

    args = parser.parse_args(argv)
    if args.command == "examples":
        scorer = UIClipScorer() if args.uiclip else None
        write_table(run_examples(args.pages, args.build, uiclip=scorer), args.out)
        return 0
    if args.command == "perturbations":
        from .perturbations import run_perturbations, write_report

        scorer = None if args.no_uiclip else UIClipScorer()
        rows = run_perturbations(args.pages, args.build, uiclip=scorer)
        print(write_report(rows, args.out))
        return 0

    reference = Reference.model_validate_json(args.reference.read_text("utf-8"))
    with Renderer() as renderer:
        row, _ = measure(
            renderer,
            reference,
            args.reference_png,
            args.generated,
            args.generated.stem,
            args.workdir,
            uiclip=UIClipScorer() if args.uiclip else None,
        )
    write_table([row], args.out)
    return 0 if row.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
