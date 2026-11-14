# Evaluation toolkit (first milestone)

> **Work in progress.** This repository accompanies a research paper that is still being
> written. The method, the thresholds and the code may change. **Nothing here is a result
> of the study**: every number this repository can produce today comes from small
> synthetic examples written to test the pipeline.

EduFidelity is a salience-aware, human-calibrated approach for evaluating e-learning
interfaces that a Large Language Model generated from a human-authored reference design.

Visual and structural similarity tell whether a generated page *looks like* its reference.
They do not tell whether what went wrong *matters* for the learning activity. Losing a
decorative illustration and losing the submit button of an assessment are both "one
missing element". EduFidelity keeps them apart.

## What it measures

Automatic evidence, computed and reported separately:

| Evidence | Measure | Status |
|---|---|---|
| Visual fidelity | SSIM between reference and generated screenshots | available |
| Visual fidelity | UIClip embedding similarity | planned (M1) |
| Structural fidelity | Element Preservation: precision, recall, F1 over matched elements | available |
| Structural fidelity | Layout Fidelity: mean IoU of matched elements | available |
| Salience-conditioned preservation | Share of *Essential*, *Supporting* and *Decorative* reference elements preserved | available |

Pedagogical salience is annotated on the **reference** only, before any generated output
exists, from a task brief that states what the learner must do on that page:

- **Essential**: removing it prevents the learner from interpreting, performing, navigating or completing the activity.
- **Supporting**: removing it does not prevent completion but reduces comprehension, orientation, feedback or context.
- **Decorative**: removing it only changes visual presentation.

The composite score is **not** a hand-weighted sum. It will be calibrated against
multidisciplinary human judgments with an ordinal model and validated on educational
domains left out of calibration (planned, M3).

## How it works today

```
reference (elements + screenshot) ─┐
generated page (HTML) ──> controlled render ──> screenshot + DOM elements
                                   └──> one-to-one matching ──> measures ──> one table row
```

- **Controlled rendering** (`render.py`): pinned Chromium, viewport equal to the reference
  frame, scale factor 1, animations off, network closed. A page is captured only after
  fonts and images are ready and the layout is stable. A page that never settles is
  recorded as a `render_failure`; it is never dropped.
- **Element collection** (`collector.py`): text, graphics and controls, with no dependence
  on instrumentation of the generated page.
- **Matching** (`matching.py`): minimum-cost one-to-one assignment over content and spatial
  disagreement, gated by element type. A greedy IoU baseline is kept for comparison.
  **The matching parameters are provisional**; they will be tuned on a development sample
  with manually verified correspondences and then frozen. Their digest is stored in every
  row.
- **Undefined is not zero**: a salience category with no eligible elements yields an empty
  value.

## Try it

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run playwright install chromium
uv run edufidelity examples
uv run pytest
```

`edufidelity examples` renders three pages of a fictitious course, derives four variants
of each (a faithful copy, one with an Essential element removed, one with an element
displaced, one without decoration), and prints one row per variant.

## Synthetic examples (not study results)

| Page / variant | SSIM | EP F1 | Layout | Essential | Supporting | Decorative |
|---|---:|---:|---:|---:|---:|---:|
| lesson / faithful | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| lesson / missing_essential | 0.991 | 0.947 | 0.911 | 0.750 | 1.000 | 1.000 |
| lesson / shifted | 0.977 | 1.000 | 0.900 | 1.000 | 1.000 | 1.000 |
| lesson / no_decorative | 0.833 | 0.889 | 0.214 | 1.000 | 1.000 | 0.000 |
| quiz / faithful | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| quiz / missing_essential | 0.993 | 0.963 | 0.923 | 0.875 | 1.000 | 1.000 |
| quiz / shifted | 0.986 | 1.000 | 0.929 | 1.000 | 1.000 | 1.000 |
| quiz / no_decorative | 0.890 | 0.923 | 0.109 | 1.000 | 1.000 | 0.000 |
| overview / faithful | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| overview / missing_essential | 0.957 | 0.963 | 0.894 | 0.800 | 1.000 | 1.000 |
| overview / shifted | 0.984 | 1.000 | 0.931 | 1.000 | 1.000 | 1.000 |
| overview / no_decorative | 0.848 | 0.923 | 0.052 | 1.000 | 1.000 | 0.000 |

Produced by `edufidelity examples` on Windows with the provisional matching parameters.
Values depend on the fonts installed and are not expected to match across systems until
fonts are bundled (M1).

Read as a sanity check: the faithful copy scores the maximum everywhere; removing an
Essential element shows up in the Essential column and not in the Decorative one; a
displaced element lowers Layout Fidelity and leaves preservation intact.

One thing these examples already show is worth stating plainly. In the `no_decorative`
rows, Layout Fidelity collapses although every Essential and Supporting element is
present: removing the header logo makes the rest of the page move up a few pixels, and
the mean IoU of small, tight text boxes drops to almost zero under any uniform shift.
Mean IoU, as defined, is brittle to reflow. Whether to report it next to a
shift-tolerant variant is an open methodological question, tracked in the engineering
plan.

## What is not here

- **The generation pipeline.** The interfaces in the study are produced by a proprietary
  platform. This repository covers evaluation only.
- **The study corpus.** The course designs and contents belong to third parties.
- **Results.** They will be released with the paper.

## Roadmap

| Milestone | Scope |
|---|---|
| M0 (this version) | Contracts, controlled rendering, collection, matching, Element Preservation, Layout Fidelity, salience-conditioned preservation, SSIM, synthetic examples, CI |
| M1 | UIClip similarity and its validation under controlled perturbations; design-file exporter to the reference format |
| M2 | Salience annotation guide, task-brief template, annotation and rating kit, inter-rater agreement |
| M3 | Ordinal calibration, leave-one-domain-out validation, ablation, clustered bootstrap |
| M4 | Frozen matching parameters from a verified development sample; supplementary material |
| M5 | Release with the paper |

Details in [docs/engineering-plan.md](engineering-plan.md).
