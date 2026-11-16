"""Verified correspondences: the development sample that tunes and freezes the matching.

A person checks the pairs the matcher proposed on a static review page, corrects them,
and saves the verified pairs. Precision and recall of the matcher are computed against
those pairs. The development sample must not overlap with the study's interfaces.

Folder layout of a development sample (one sub-folder per generated page)::

    dev/<item>/reference.json   reference representation
    dev/<item>/snapshot.json    elements collected from the rendered generated page
    dev/<item>/verified.json    pairs confirmed by a person (or derived, for synthetic pages)
    dev/<item>/review.html      the page used to verify them
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from .models import Correspondence, DomSnapshot, Element, Reference


class VerifiedPairs(BaseModel):
    interface_id: str
    generated_id: str
    pairs: list[tuple[str, str]]  # (reference element id, generated element id)
    verifier: str
    source: Literal["manual", "synthetic"]
    note: str = ""

    def digest(self) -> str:
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PairScores:
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float | None:
        found = self.true_positive + self.false_positive
        return self.true_positive / found if found else None

    @property
    def recall(self) -> float | None:
        expected = self.true_positive + self.false_negative
        return self.true_positive / expected if expected else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 2 * p * r / (p + r) if p + r else 0.0

    def __add__(self, other: PairScores) -> PairScores:
        return PairScores(self.true_positive + other.true_positive,
                          self.false_positive + other.false_positive,
                          self.false_negative + other.false_negative)


def pair_scores(predicted: Correspondence, gold: VerifiedPairs) -> PairScores:
    found = {(m.ref_id, m.gen_id) for m in predicted.matches}
    expected = {tuple(p) for p in gold.pairs}
    return PairScores(len(found & expected), len(found - expected), len(expected - found))


def pooled(scores: Sequence[PairScores]) -> PairScores:
    total = PairScores(0, 0, 0)
    for s in scores:
        total = total + s
    return total


class DevItem(BaseModel):
    name: str
    reference: Reference
    snapshot: DomSnapshot
    verified: VerifiedPairs


def load_dev_sample(folder: Path) -> list[DevItem]:
    """Every sub-folder with the three files. A folder without ``verified.json`` is an
    unfinished verification and is reported, not silently skipped."""
    items, unfinished = [], []
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        if not (sub / "verified.json").exists():
            unfinished.append(sub.name)
            continue
        items.append(DevItem(
            name=sub.name,
            reference=Reference.model_validate_json((sub / "reference.json").read_text("utf-8")),
            snapshot=DomSnapshot.model_validate_json((sub / "snapshot.json").read_text("utf-8")),
            verified=VerifiedPairs.model_validate_json((sub / "verified.json").read_text("utf-8")),
        ))
    if unfinished:
        raise ValueError(f"unverified items in {folder}: {', '.join(unfinished)}")
    if not items:
        raise ValueError(f"no development items in {folder}")
    return items


def sample_digest(items: Sequence[DevItem]) -> str:
    parts = sorted(f"{i.name}:{i.reference.digest()}:{i.verified.digest()}" for i in items)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ review page

def _data_uri(png: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")


_REVIEW_JS = r"""
const data = JSON.parse(document.getElementById('data').textContent);
const rows = document.querySelectorAll('tr[data-ref]');
const mark = (side, id, on) => {
  const el = document.querySelector(`.box[data-side="${side}"][data-id="${id}"]`);
  if (el) el.classList.toggle('on', on);
};
rows.forEach((row) => {
  const select = row.querySelector('select');
  const show = (on) => { mark('ref', row.dataset.ref, on); if (select.value) mark('gen', select.value, on); };
  row.addEventListener('mouseenter', () => show(true));
  row.addEventListener('mouseleave', () => show(false));
  select.addEventListener('change', () => row.classList.toggle('changed',
    select.value !== row.dataset.proposed));
});
document.getElementById('save').addEventListener('click', () => {
  const verifier = document.getElementById('verifier').value.trim();
  if (!verifier) { alert('Write your name or initials first.'); return; }
  const chosen = Array.from(rows).filter((r) => r.querySelector('select').value)
    .map((r) => [r.dataset.ref, r.querySelector('select').value]);
  const used = chosen.map((p) => p[1]);
  if (new Set(used).size !== used.length) { alert('A generated element is paired twice.'); return; }
  const out = { interface_id: data.interface_id, generated_id: data.generated_id,
    pairs: chosen, verifier, source: 'manual',
    note: document.getElementById('note').value.trim() };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'verified.json'; a.click();
});
"""


def review_page(
    reference: Reference,
    snapshot: DomSnapshot,
    proposed: Correspondence,
    reference_png: Path,
    generated_png: Path,
    generated_id: str,
) -> str:
    """A self-contained HTML page (images embedded, no network) to verify the pairs."""
    proposed_of = {m.ref_id: m.gen_id for m in proposed.matches}
    by_type: dict[str, list[tuple[str, str]]] = {}
    for g in snapshot.elements:
        by_type.setdefault(g.type.value, []).append((g.id, g.text[:40] or f"({g.type.value})"))

    def boxes(side: str, elements: Sequence[Element], png: Path) -> str:
        with Image.open(png) as image:
            height = image.height
        out = []
        for e in elements:
            b = e.bbox
            # boxes are normalized by the reference frame; the screenshot may be taller
            top = b.y * reference.frame_height / height * 100
            hgt = b.h * reference.frame_height / height * 100
            out.append(f'<div class="box" data-side="{side}" data-id="{html.escape(e.id)}" '
                       f'style="left:{b.x * 100:.3f}%;top:{top:.3f}%;width:{b.w * 100:.3f}%;'
                       f'height:{hgt:.3f}%"></div>')
        return "".join(out)

    rows = []
    for r in reference.elements:
        options = ['<option value="">— no pair (missing) —</option>']
        for gid, text in by_type.get(r.type.value, []):
            selected = " selected" if proposed_of.get(r.id) == gid else ""
            options.append(f'<option value="{html.escape(gid)}"{selected}>'
                           f'{html.escape(gid)} · {html.escape(text)}</option>')
        proposed_id = html.escape(proposed_of.get(r.id, ""))
        rows.append(
            f'<tr data-ref="{html.escape(r.id)}" data-proposed="{proposed_id}">'
            f"<td>{html.escape(r.id)}</td><td>{r.type.value}</td>"
            f"<td>{html.escape(r.text[:60])}</td><td><select>{''.join(options)}</select></td></tr>")
    payload = json.dumps({"interface_id": reference.interface_id, "generated_id": generated_id})
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Verify pairs · {html.escape(generated_id)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }}
  .shots {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .shot {{ position: relative; border: 1px solid #cbd2d9; }}
  .shot img {{ width: 100%; display: block; }}
  .box {{ position: absolute; border: 1px solid rgba(47, 133, 90, .35); }}
  .box.on {{ border: 3px solid #d64545; background: rgba(214, 69, 69, .12); }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 14px; }}
  td, th {{ border-bottom: 1px solid #e4e7eb; padding: 4px 8px; text-align: left; }}
  tr.changed {{ background: #fff7e6; }}
  select {{ max-width: 420px; }}
  .bar {{ position: sticky; top: 0; background: #fff; padding: 8px 0; display: flex; gap: 8px; }}
</style></head><body>
<h1>Verify pairs · {html.escape(reference.interface_id)} → {html.escape(generated_id)}</h1>
<p>For each reference element, choose the generated element that is <b>the same element</b>,
or "no pair" if it is missing. Hover a row to see both boxes. Rows you change turn yellow.
Save, and put <code>verified.json</code> next to this page.</p>
<div class="bar"><input id="verifier" placeholder="your name or initials">
<input id="note" placeholder="note (optional)" size="40"><button id="save">Save verified.json</button></div>
<div class="shots">
  <div><h2>Reference</h2><div class="shot"><img src="{_data_uri(reference_png)}" alt="reference">
  {boxes("ref", reference.elements, reference_png)}</div></div>
  <div><h2>Generated</h2><div class="shot"><img src="{_data_uri(generated_png)}" alt="generated">
  {boxes("gen", snapshot.elements, generated_png)}</div></div>
</div>
<table><tr><th>Reference id</th><th>Type</th><th>Text</th><th>Same element in the generated page</th></tr>
{"".join(rows)}</table>
<script type="application/json" id="data">{payload}</script>
<script>{_REVIEW_JS}</script>
</body></html>
"""
