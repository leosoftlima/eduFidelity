"""Command-line part of M4: verify pairs, tune and freeze the matching."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .matching import match_optimal
from .models import DomSnapshot, Reference

COMMANDS = ("review-pairs", "dev-sample-synthetic", "tune-matching", "freeze-matching")


def register(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    rev = commands.add_parser("review-pairs", help="page to verify the proposed pairs by hand")
    rev.add_argument("reference", type=Path, help="reference JSON")
    rev.add_argument("reference_png", type=Path)
    rev.add_argument("snapshot", type=Path, help="<generated>.snapshot.json from measure")
    rev.add_argument("generated_png", type=Path)
    rev.add_argument("--config", type=Path, default=None, help="matching configuration JSON")
    rev.add_argument("--out", type=Path, required=True, help="item folder in the dev sample")

    syn = commands.add_parser("dev-sample-synthetic",
                              help="development sample from the synthetic pages (pairs known)")
    syn.add_argument("--pages", type=Path, default=Path("examples/pages"))
    syn.add_argument("--build", type=Path, default=Path("examples/_build/dev-build"))
    syn.add_argument("--out", type=Path, default=Path("examples/_build/dev-sample"))

    tun = commands.add_parser("tune-matching", help="evaluate the grid on a dev sample")
    tun.add_argument("sample", type=Path, help="development sample folder")
    tun.add_argument("--out", type=Path, default=Path("supplementary/matching"))

    frz = commands.add_parser("freeze-matching", help="freeze the best configuration")
    frz.add_argument("sample", type=Path, help="development sample folder")
    frz.add_argument("--study-interfaces", type=Path, required=True,
                     help="text file, one reference interface id of the study per line")
    frz.add_argument("--note", default="")
    frz.add_argument("--out", type=Path, required=True, help="frozen configuration JSON")


def run(args: argparse.Namespace) -> int:
    from .tuning import freeze, load_config, report, tune
    from .verification import load_dev_sample, review_page

    if args.command == "review-pairs":
        reference = Reference.model_validate_json(args.reference.read_text("utf-8"))
        snapshot = DomSnapshot.model_validate_json(args.snapshot.read_text("utf-8"))
        config = load_config(args.config) if args.config else None
        proposed = match_optimal(reference.elements, snapshot.elements, config)
        generated_id = args.snapshot.name.removesuffix(".snapshot.json")
        args.out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.reference, args.out / "reference.json")
        shutil.copyfile(args.snapshot, args.out / "snapshot.json")
        page = review_page(reference, snapshot, proposed, args.reference_png,
                           args.generated_png, generated_id)
        (args.out / "review.html").write_text(page, encoding="utf-8")
        print(f"open {args.out / 'review.html'} and save verified.json into {args.out}")
        return 0

    if args.command == "dev-sample-synthetic":
        from .devsample import synthetic_dev_sample

        folders = synthetic_dev_sample(args.pages, args.build, args.out)
        print(f"{len(folders)} synthetic items in {args.out}")
        return 0

    items = load_dev_sample(args.sample)
    result = tune(items)
    if args.command == "tune-matching":
        sources = {i.verified.source for i in items}
        banner = ("> **SYNTHETIC development sample: pairs known by construction, defects "
                  "injected on purpose.** It exercises the procedure; it cannot choose the "
                  "parameters for real generated pages." if sources == {"synthetic"} else
                  f"> Development sample `{args.sample}`.")
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "README.md").write_text(report(result, items, banner), encoding="utf-8")
        print(args.out / "README.md")
        return 0

    if args.command == "freeze-matching":
        study = {line.strip() for line in args.study_interfaces.read_text("utf-8").splitlines()
                 if line.strip()}
        frozen = freeze(result, items, study, note=args.note)
        if frozen.dev_sources != ["manual"]:
            print("warning: the development sample is not (only) manually verified")
        args.out.write_text(frozen.model_dump_json(indent=2), encoding="utf-8")
        print(f"{args.out}  configuration {frozen.config_digest}  "
              f"sample {frozen.dev_sample_digest}  F1 {frozen.f1}")
        return 0
    raise SystemExit(f"unknown command {args.command}")
