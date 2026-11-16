"""End-to-end steps: build a synthetic reference, measure a generated page."""

from __future__ import annotations

from pathlib import Path

from .matching import match_optimal
from .measures import (
    UIClipScorer,
    element_preservation,
    layout_fidelity,
    pedagogical_preservation,
    ssim_score,
)
from .models import (
    BBox,
    Correspondence,
    ElementType,
    MatchConfig,
    MeasureRow,
    RefElement,
    Reference,
    Salience,
)
from .render import Renderer, to_snapshot

_PROBE_HEIGHT = 800


class ReferenceAuthoringError(ValueError):
    """The authored reference is incomplete or inconsistent."""


def build_reference_from_html(
    renderer: Renderer,
    html: Path,
    interface_id: str,
    frame_width: int,
    screenshot: Path,
    *,
    domain: str = "",
    course: str = "",
) -> Reference:
    """Build a Reference from a hand-authored HTML page (synthetic examples only).

    Every collected element must carry ``data-ref-id`` and ``data-salience``: an
    unlabeled element is an error, so a reference can never be partially annotated.
    Real references come from design files, not from this function.
    """
    record, raw = renderer.render(html, frame_width, _PROBE_HEIGHT, reference_mode=True)
    if raw is None:
        raise ReferenceAuthoringError(f"{html}: {record.reason}")
    frame_height = int(raw["pageHeight"])
    record, raw = renderer.render(
        html, frame_width, frame_height, screenshot, reference_mode=True
    )
    if raw is None:
        raise ReferenceAuthoringError(f"{html}: {record.reason}")

    elements: list[RefElement] = []
    seen: set[str] = set()
    for item in raw["elements"]:
        ref_id, salience = item.get("refId"), item.get("salience")
        label = f"<{item['tag']}> {item.get('text', '')[:40]!r}"
        if not ref_id or not salience:
            raise ReferenceAuthoringError(f"{html}: {label} lacks data-ref-id or data-salience")
        if ref_id in seen:
            raise ReferenceAuthoringError(f"{html}: duplicated data-ref-id {ref_id!r}")
        seen.add(ref_id)
        elements.append(
            RefElement(
                id=ref_id,
                type=ElementType(item["type"]),
                text=item.get("text") or "",
                bbox=BBox(x=item["x"], y=item["y"], w=item["w"], h=item["h"]),
                asset=item.get("asset"),
                salience=Salience(salience),
            )
        )
    return Reference(
        interface_id=interface_id,
        domain=domain,
        course=course,
        frame_width=frame_width,
        frame_height=frame_height,
        elements=elements,
    )


def measure(
    renderer: Renderer,
    reference: Reference,
    reference_png: Path,
    generated_html: Path | str,
    generated_id: str,
    workdir: Path,
    config: MatchConfig | None = None,
    uiclip: UIClipScorer | None = None,
) -> tuple[MeasureRow, Correspondence | None]:
    """Render a generated page and compute every measure against its reference.

    UIClip is computed only when a scorer is given (it needs the optional extra).
    """
    config = config or MatchConfig()
    row = MeasureRow(
        interface_id=reference.interface_id,
        generated_id=generated_id,
        domain=reference.domain,
        n_reference=len(reference.elements),
        config_digest=config.digest(),
        reference_digest=reference.digest(),
    )
    screenshot = workdir / f"{generated_id}.png"
    record, raw = renderer.render(
        generated_html, reference.frame_width, reference.frame_height, screenshot
    )
    if raw is None:
        row.status = f"render_failure: {record.reason}"
        return row, None

    snapshot = to_snapshot(raw, reference.frame_width, reference.frame_height)
    # kept so that the pairs can be verified later (development sample, M4)
    (workdir / f"{generated_id}.snapshot.json").write_text(
        snapshot.model_dump_json(indent=2), encoding="utf-8")
    correspondence = match_optimal(reference.elements, snapshot.elements, config)
    scores = element_preservation(
        correspondence, len(reference.elements), len(snapshot.elements)
    )
    ped = pedagogical_preservation(reference.elements, correspondence)

    row.n_generated = len(snapshot.elements)
    row.n_matched = len(correspondence.matches)
    row.ep_precision, row.ep_recall, row.ep_f1 = scores.precision, scores.recall, scores.f1
    row.layout_fidelity = layout_fidelity(correspondence, len(reference.elements))
    row.ped_essential = ped[Salience.ESSENTIAL]
    row.ped_supporting = ped[Salience.SUPPORTING]
    row.ped_decorative = ped[Salience.DECORATIVE]
    row.ssim = ssim_score(reference_png, screenshot)
    if uiclip is not None:
        comparison = uiclip.compare(reference_png, screenshot)
        row.uiclip = comparison.similarity
        row.uiclip_worst_band = comparison.worst_band
        row.uiclip_checkpoint = uiclip.checkpoint
    return row, correspondence
