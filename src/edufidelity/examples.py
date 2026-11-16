"""Synthetic examples: a fictitious course with controlled defects.

Each page is a hand-authored reference. Variants are derived from it by removing or
displacing named elements, then stripping every authoring attribute, so a variant
carries no trace of the reference ids. The numbers these examples produce are a
sanity check of the pipeline. THEY ARE NOT RESULTS OF THE STUDY.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .measures import UIClipScorer
from .models import MeasureRow
from .pipeline import build_reference_from_html, measure
from .render import Renderer

_VARIANT_JS = r"""
(spec) => {
  for (const id of spec.remove || []) {
    const el = document.querySelector(`[data-ref-id="${id}"]`);
    if (!el) throw new Error(`unknown element: ${id}`);
    el.remove();
  }
  for (const [id, css] of Object.entries(spec.style || {})) {
    const el = document.querySelector(`[data-ref-id="${id}"]`);
    if (!el) throw new Error(`unknown element: ${id}`);
    el.setAttribute('style', (el.getAttribute('style') || '') + ';' + css);
  }
  for (const el of document.querySelectorAll('[data-ref-id], [data-salience]')) {
    el.removeAttribute('data-ref-id');
    el.removeAttribute('data-salience');
  }
  // The variant is written elsewhere: keep relative resources (the bundled fonts)
  // resolving against the original page.
  const base = document.createElement('base');
  base.href = location.href;
  document.head.prepend(base);
  return '<!doctype html>\n' + document.documentElement.outerHTML;
}
"""


def make_variants(pages_dir: Path, build_dir: Path) -> dict[str, dict[str, Path]]:
    """Write every variant of every page; returns {page: {variant: html path}}."""
    manifest: dict[str, Any] = json.loads((pages_dir / "pages.json").read_text("utf-8"))
    written: dict[str, dict[str, Path]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for name, entry in manifest["pages"].items():
            written[name] = {}
            for variant, spec in entry["variants"].items():
                page.goto((pages_dir / entry["file"]).resolve().as_uri())
                html: str = page.evaluate(_VARIANT_JS, spec)
                target = build_dir / name / f"{variant}.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")
                written[name][variant] = target
        browser.close()
    return written


def run_examples(
    pages_dir: Path, build_dir: Path, uiclip: UIClipScorer | None = None
) -> list[MeasureRow]:
    """Build references and variants, measure everything, return the table."""
    manifest: dict[str, Any] = json.loads((pages_dir / "pages.json").read_text("utf-8"))
    variants = make_variants(pages_dir, build_dir)
    rows: list[MeasureRow] = []
    with Renderer() as renderer:
        for name, entry in manifest["pages"].items():
            out = build_dir / name
            reference_png = out / "reference.png"
            reference = build_reference_from_html(
                renderer,
                pages_dir / entry["file"],
                interface_id=name,
                frame_width=manifest["frame_width"],
                screenshot=reference_png,
                domain="synthetic",
                course=manifest["course"],
            )
            (out / "reference.json").write_text(
                reference.model_dump_json(indent=2), encoding="utf-8"
            )
            for variant, html in variants[name].items():
                row, correspondence = measure(
                    renderer,
                    reference,
                    reference_png,
                    html,
                    f"{name}--{variant}",
                    out,
                    uiclip=uiclip,
                )
                if correspondence is not None:
                    (out / f"{variant}.correspondence.json").write_text(
                        correspondence.model_dump_json(indent=2), encoding="utf-8"
                    )
                rows.append(row)
    return rows
