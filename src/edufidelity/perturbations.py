"""Perturbation study: does each measure move when, and only when, it should?

Every synthetic reference page is degraded in controlled ways (remove, shift, recolor,
change font, zoom, truncate, blank), at graded intensities where that makes sense. Each
degraded page is measured against its reference with every measure.

The question is not whether a number is "good". It is whether a measure *responds* to
the defects it claims to capture, and stays put under the ones it does not. The
expectations are written below, before the study runs; the report states every case
where a measure does not move as expected. THESE ARE SYNTHETIC PAGES, NOT STUDY RESULTS.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from .measures import UIClipScorer
from .models import MeasureRow
from .pipeline import build_reference_from_html, measure
from .render import Renderer

VISUAL = ("ssim", "uiclip")
MEASURES = (
    "ssim", "uiclip", "ep_f1", "layout_fidelity",
    "ped_essential", "ped_supporting", "ped_decorative",
)


@dataclass(frozen=True)
class Perturbation:
    name: str
    family: str
    level: int  # order of intensity inside the family
    spec: dict[str, Any]
    #: Measures expected to fall below the identity value. Written before running.
    should_drop: tuple[str, ...] = field(default=())


PERTURBATIONS: tuple[Perturbation, ...] = (
    Perturbation("identity", "identity", 0, {}),
    Perturbation("remove-decorative", "remove", 1, {"remove": "decorative"},
                 (*VISUAL, "ep_f1", "layout_fidelity", "ped_decorative")),
    Perturbation("remove-supporting", "remove", 2, {"remove": "supporting"},
                 (*VISUAL, "ep_f1", "layout_fidelity", "ped_supporting")),
    Perturbation("remove-essential", "remove", 3, {"remove": "essential"},
                 (*VISUAL, "ep_f1", "layout_fidelity", "ped_essential")),
    Perturbation("shift-8px", "shift", 1, {"shift": 8}, (*VISUAL, "layout_fidelity")),
    Perturbation("shift-32px", "shift", 2, {"shift": 32}, (*VISUAL, "layout_fidelity")),
    Perturbation("shift-128px", "shift", 3, {"shift": 128}, (*VISUAL, "layout_fidelity")),
    Perturbation("hue-45deg", "recolor", 1, {"filter": "hue-rotate(45deg)"}, VISUAL),
    Perturbation("hue-180deg", "recolor", 2, {"filter": "hue-rotate(180deg)"}, VISUAL),
    Perturbation("serif-font", "font", 1, {"font": "EduSerif"}, (*VISUAL, "layout_fidelity")),
    Perturbation("zoom-115", "zoom", 1, {"zoom": 1.15}, (*VISUAL, "layout_fidelity")),
    Perturbation("truncate-half", "truncate", 1, {"truncate": 0.5},
                 (*VISUAL, "ep_f1", "layout_fidelity")),
    Perturbation("blank", "blank", 1, {"blank": True}, MEASURES),
)

_PERTURB_JS = r"""
(spec) => {
  const labeled = (salience) => Array.from(document.querySelectorAll(
    `[data-salience="${salience}"]`));
  const area = (el) => { const r = el.getBoundingClientRect(); return r.width * r.height; };
  const largest = (salience) => {
    const items = labeled(salience);
    if (!items.length) throw new Error(`no ${salience} element`);
    return items.reduce((a, b) => (area(b) > area(a) ? b : a));
  };
  const addStyle = (css) => {
    const s = document.createElement('style'); s.textContent = css; document.head.append(s);
  };
  if (spec.remove) largest(spec.remove).remove();
  if (spec.shift) {
    const el = largest('essential');
    el.setAttribute('style', (el.getAttribute('style') || '') +
      `;position:relative;left:${spec.shift}px;top:${spec.shift}px`);
  }
  if (spec.filter) addStyle(`html { filter: ${spec.filter}; }`);
  if (spec.font) addStyle(`body, button, input { font-family: "${spec.font}", serif !important; }`);
  if (spec.zoom) addStyle(`body { zoom: ${spec.zoom}; }`);
  if (spec.truncate) {
    const cut = document.documentElement.scrollHeight * spec.truncate;
    for (const el of Array.from(document.querySelectorAll('[data-ref-id]'))) {
      if (el.isConnected && el.getBoundingClientRect().top + window.scrollY >= cut) el.remove();
    }
  }
  if (spec.blank) document.body.innerHTML = '';
  for (const el of document.querySelectorAll('[data-ref-id], [data-salience]')) {
    el.removeAttribute('data-ref-id');
    el.removeAttribute('data-salience');
  }
  const base = document.createElement('base');
  base.href = location.href;
  document.head.prepend(base);
  return '<!doctype html>\n' + document.documentElement.outerHTML;
}
"""


@dataclass(frozen=True)
class PerturbationRow:
    page: str
    perturbation: Perturbation
    row: MeasureRow
    screenshot: Path

    def value(self, measure_name: str) -> float | None:
        value = getattr(self.row, measure_name)
        return None if value is None else float(value)


def write_perturbed_pages(
    pages_dir: Path, build_dir: Path, perturbations: Sequence[Perturbation] = PERTURBATIONS
) -> dict[str, dict[str, Path]]:
    manifest: dict[str, Any] = json.loads((pages_dir / "pages.json").read_text("utf-8"))
    written: dict[str, dict[str, Path]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": manifest["frame_width"], "height": 800})
        for name, entry in manifest["pages"].items():
            written[name] = {}
            for perturbation in perturbations:
                page.goto((pages_dir / entry["file"]).resolve().as_uri())
                page.evaluate("document.fonts.ready")
                html: str = page.evaluate(_PERTURB_JS, perturbation.spec)
                target = build_dir / name / f"{perturbation.name}.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")
                written[name][perturbation.name] = target
        browser.close()
    return written


def run_perturbations(
    pages_dir: Path,
    build_dir: Path,
    uiclip: UIClipScorer | None = None,
    perturbations: Sequence[Perturbation] = PERTURBATIONS,
) -> list[PerturbationRow]:
    manifest: dict[str, Any] = json.loads((pages_dir / "pages.json").read_text("utf-8"))
    pages = write_perturbed_pages(pages_dir, build_dir, perturbations)
    rows: list[PerturbationRow] = []
    with Renderer() as renderer:
        for name, entry in manifest["pages"].items():
            out = build_dir / name
            reference_png = out / "reference.png"
            reference = build_reference_from_html(
                renderer, pages_dir / entry["file"], interface_id=name,
                frame_width=manifest["frame_width"], screenshot=reference_png,
                domain="synthetic", course=manifest["course"],
            )
            for perturbation in perturbations:
                generated_id = f"{name}--{perturbation.name}"
                row, _ = measure(renderer, reference, reference_png,
                                 pages[name][perturbation.name], generated_id, out,
                                 uiclip=uiclip)
                rows.append(PerturbationRow(name, perturbation, row, out / f"{generated_id}.png"))
    return rows


# ------------------------------------------------------------------ verdicts and report

_EPS = 1e-6


@dataclass(frozen=True)
class Verdict:
    page: str
    perturbation: str
    measure: str
    expected_drop: bool
    identity: float | None
    value: float | None

    @property
    def dropped(self) -> bool | None:
        if self.identity is None or self.value is None:
            return None
        return self.value < self.identity - _EPS

    @property
    def as_expected(self) -> bool | None:
        dropped = self.dropped
        return None if dropped is None else dropped == self.expected_drop


def verdicts(rows: Sequence[PerturbationRow]) -> list[Verdict]:
    identity = {r.page: r for r in rows if r.perturbation.family == "identity"}
    found = []
    for r in rows:
        if r.perturbation.family == "identity":
            continue
        for name in MEASURES:
            found.append(Verdict(
                page=r.page, perturbation=r.perturbation.name, measure=name,
                expected_drop=name in r.perturbation.should_drop,
                identity=identity[r.page].value(name), value=r.value(name),
            ))
    return found


def monotonicity(rows: Sequence[PerturbationRow]) -> list[tuple[str, str, str, bool]]:
    """(page, family, measure, non-increasing with intensity) for graded families."""
    out = []
    pages = sorted({r.page for r in rows})
    for family in ("shift", "recolor"):
        for page in pages:
            graded = sorted((r for r in rows if r.page == page and r.perturbation.family == family),
                            key=lambda r: r.perturbation.level)
            for name in MEASURES:
                values = [r.value(name) for r in graded]
                if len(values) < 2 or any(v is None for v in values):
                    continue
                ok = all(b <= a + _EPS for a, b in zip(values, values[1:], strict=False))  # type: ignore[operator]
                out.append((page, family, name, ok))
    return out


def _fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.3f}"


def write_report(
    rows: Sequence[PerturbationRow], out_dir: Path, *, sheet_page: str = "lesson"
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["page", "perturbation", "family", "level", *MEASURES, "uiclip_worst_band",
              "uiclip_checkpoint", "status"]
    with (out_dir / "perturbations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            record: dict[str, Any] = {"page": r.page, "perturbation": r.perturbation.name,
                                      "family": r.perturbation.family,
                                      "level": r.perturbation.level, "status": r.row.status,
                                      "uiclip_checkpoint": r.row.uiclip_checkpoint}
            for name in (*MEASURES, "uiclip_worst_band"):
                value = getattr(r.row, name)
                record[name] = "" if value is None else f"{value:.4f}"
            writer.writerow(record)

    contact_sheet([r for r in rows if r.page == sheet_page], out_dir / f"{sheet_page}.png")
    found = verdicts(rows)
    graded = monotonicity(rows)
    pages = sorted({r.page for r in rows})
    has_uiclip = any(r.row.uiclip is not None for r in rows)
    checkpoint = next((r.row.uiclip_checkpoint for r in rows if r.row.uiclip_checkpoint), "")

    lines = [
        "# Perturbation study",
        "",
        "> Synthetic pages of a fictitious course. **Not results of the study.** Generated by",
        "> `edufidelity perturbations`; every number below comes from `perturbations.csv`.",
        "",
        f"Pages: {', '.join(pages)}. Perturbations: {len(PERTURBATIONS) - 1} plus identity. "
        + (f"UIClip checkpoint: `{checkpoint}`." if has_uiclip else "UIClip not computed."),
        "",
        f"![Perturbations of the {sheet_page} page]({sheet_page}.png)",
        "",
        "## Mean over pages",
        "",
        "| Perturbation | " + " | ".join(MEASURES) + " |",
        "|---|" + "---:|" * len(MEASURES),
    ]
    for p in PERTURBATIONS:
        cells = []
        for name in MEASURES:
            values = [r.value(name) for r in rows if r.perturbation.name == p.name]
            present = [v for v in values if v is not None]
            text = _fmt(mean(present)) if present else "–"
            cells.append(f"**{text}**" if name in p.should_drop else text)
        lines.append(f"| {p.name} | " + " | ".join(cells) + " |")
    lines += ["", "Bold: the measure is expected to fall for that perturbation (expectations "
              "are fixed in `perturbations.py` before running).", ""]

    lines += ["## Where a measure did not behave as expected", ""]
    misses = [v for v in found if v.as_expected is False]
    if not misses:
        lines.append("None: every measure fell where expected and stayed put elsewhere.")
    else:
        lines += ["| Page | Perturbation | Measure | Expected | Identity | Value |",
                  "|---|---|---|---|---:|---:|"]
        for v in misses:
            expected = "drop" if v.expected_drop else "no drop"
            lines.append(f"| {v.page} | {v.perturbation} | {v.measure} | {expected} | "
                         f"{_fmt(v.identity)} | {_fmt(v.value)} |")
    checked = [v for v in found if v.as_expected is not None]
    lines += ["", f"{sum(v.as_expected is True for v in checked)} of {len(checked)} checks "
              "as expected.", ""]

    lines += ["## Graded perturbations", "",
              "A measure should not improve as the same defect gets stronger.", ""]
    broken = [g for g in graded if not g[3]]
    if not broken:
        lines.append(f"Non-increasing in all {len(graded)} graded series.")
    else:
        for page, family, name, _ in broken:
            lines.append(f"- {page} / {family} / {name}: not monotonic.")
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_dir / "README.md"


def contact_sheet(rows: Sequence[PerturbationRow], target: Path, width: int = 220) -> None:
    """One thumbnail per perturbation, top of the page, labeled."""
    tiles = []
    for r in rows:
        with Image.open(r.screenshot) as shot:
            crop = shot.convert("RGB").crop((0, 0, shot.width, min(shot.height, shot.width)))
        thumb = crop.resize((width, int(crop.height * width / crop.width)))
        tile = Image.new("RGB", (width, thumb.height + 22), "white")
        tile.paste(thumb, (0, 22))
        ImageDraw.Draw(tile).text((4, 5), r.perturbation.name, fill=(31, 41, 51))
        tiles.append(tile)
    columns = 5
    rows_n = (len(tiles) + columns - 1) // columns
    height = max(t.height for t in tiles)
    size = (columns * (width + 8) + 8, rows_n * (height + 8) + 8)
    sheet = Image.new("RGB", size, (229, 231, 235))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (8 + (i % columns) * (width + 8), 8 + (i // columns) * (height + 8)))
    sheet.save(target)
