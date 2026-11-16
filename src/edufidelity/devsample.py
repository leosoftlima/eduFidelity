"""A development sample derived from the synthetic pages, with pairs known by construction.

The perturbed pages keep their ``data-ref-id`` attributes while being rendered, so the
true pair of every surviving element is known without a person. This exercises the
tuning and freezing code end to end. It is NOT a substitute for the verified sample of
real generated pages that M4 requires: the defects here are the ones we injected.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .matching import match_optimal
from .perturbations import PERTURBATIONS, Perturbation, write_perturbed_pages
from .pipeline import build_reference_from_html
from .render import Renderer, to_snapshot
from .verification import VerifiedPairs, review_page

#: The perturbation study plus two defects that are hard for a matcher specifically.
DEV_PERTURBATIONS: tuple[Perturbation, ...] = (
    *PERTURBATIONS,
    Perturbation("swap-essential", "reorder", 1, {"swap": True}),
    Perturbation("reword-essential", "reword", 1, {"reword": True}),
)


def synthetic_dev_sample(
    pages_dir: Path, build_dir: Path, out_dir: Path,
    perturbations: Sequence[Perturbation] = DEV_PERTURBATIONS,
) -> list[Path]:
    manifest: dict[str, Any] = json.loads((pages_dir / "pages.json").read_text("utf-8"))
    keep = [Perturbation(p.name, p.family, p.level, {**p.spec, "keepIds": True})
            for p in perturbations]
    pages = write_perturbed_pages(pages_dir, build_dir, keep)
    written: list[Path] = []
    with Renderer() as renderer:
        for name, entry in manifest["pages"].items():
            reference_png = build_dir / name / "reference.png"
            reference = build_reference_from_html(
                renderer, pages_dir / entry["file"], interface_id=name,
                frame_width=manifest["frame_width"], screenshot=reference_png,
                domain="synthetic", course=manifest["course"],
            )
            for perturbation in keep:
                generated_id = f"{name}--{perturbation.name}"
                shot = build_dir / name / f"{perturbation.name}.dev.png"
                record, raw = renderer.render(pages[name][perturbation.name],
                                              reference.frame_width, reference.frame_height,
                                              shot, reference_mode=True)
                if raw is None:
                    raise RuntimeError(f"{generated_id}: {record.reason}")
                snapshot = to_snapshot(raw, reference.frame_width, reference.frame_height)
                pairs = [(item["refId"], element.id)
                         for item, element in zip(raw["elements"], snapshot.elements, strict=True)
                         if item.get("refId")]
                verified = VerifiedPairs(
                    interface_id=name, generated_id=generated_id, pairs=pairs,
                    verifier="derived from data-ref-id", source="synthetic",
                    note="synthetic page: pairs known by construction",
                )
                folder = out_dir / generated_id
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "reference.json").write_text(reference.model_dump_json(indent=2),
                                                       encoding="utf-8")
                (folder / "snapshot.json").write_text(snapshot.model_dump_json(indent=2),
                                                      encoding="utf-8")
                (folder / "verified.json").write_text(verified.model_dump_json(indent=2),
                                                      encoding="utf-8")
                proposed = match_optimal(reference.elements, snapshot.elements)
                (folder / "review.html").write_text(
                    review_page(reference, snapshot, proposed, reference_png, shot,
                                generated_id), encoding="utf-8")
                written.append(folder)
    return written
