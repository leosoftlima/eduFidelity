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
| Visual fidelity | UIClip embedding similarity | available (optional extra) |
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
domains left out of calibration (M3: implemented and rehearsed on simulated raters, see
[Calibration](#calibration-m3)).

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

| Page / variant | SSIM | UIClip | EP F1 | Layout | Essential | Supporting | Decorative |
|---|---:|---:|---:|---:|---:|---:|---:|
| lesson / faithful | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| lesson / missing_essential | 0.990 | 0.997 | 0.947 | 0.914 | 0.750 | 1.000 | 1.000 |
| lesson / shifted | 0.975 | 0.997 | 1.000 | 0.901 | 1.000 | 1.000 | 1.000 |
| lesson / no_decorative | 0.817 | 0.988 | 0.889 | 0.222 | 1.000 | 1.000 | 0.000 |
| quiz / faithful | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| quiz / missing_essential | 0.992 | 0.997 | 0.963 | 0.923 | 0.875 | 1.000 | 1.000 |
| quiz / shifted | 0.984 | 0.996 | 1.000 | 0.929 | 1.000 | 1.000 | 1.000 |
| quiz / no_decorative | 0.880 | 0.985 | 0.923 | 0.151 | 1.000 | 1.000 | 0.000 |
| overview / faithful | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| overview / missing_essential | 0.954 | 0.999 | 0.963 | 0.895 | 0.800 | 1.000 | 1.000 |
| overview / shifted | 0.982 | 0.998 | 1.000 | 0.932 | 1.000 | 1.000 | 1.000 |
| overview / no_decorative | 0.838 | 0.990 | 0.923 | 0.062 | 1.000 | 1.000 | 0.000 |

Produced by `edufidelity examples --uiclip` with the provisional matching parameters. The
pages use bundled fonts (DejaVu, in `examples/fonts/`), so the table no longer depends on
the fonts of the machine: `examples/expected.csv` was written on Windows and the CI
checks it on Linux and Windows within a small tolerance.

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

## UIClip

UIClip is a CLIP model fine-tuned on interface screenshots (Wu et al., UIST 2024). The
measure is the cosine similarity between the embeddings of the reference and of the
generated screenshot, with the final checkpoint of the paper pinned by revision
(`biglab/uiclip_jitteredwebsites-2-224-paraphrased_webpairs_humanpairs`, MIT).

The encoder sees 224 x 224 pixels. A page is embedded the way the model authors do it:
the short side is resized to 224 px, square windows slide along the long side, and the
page embedding is the mean of the window embeddings. Squashing or center-cropping a long
page, which the default CLIP processor would do, is avoided. The similarity of the
worst-matching window band is recorded next to the score as a diagnostic.

```bash
uv sync --extra uiclip          # torch and transformers; the checkpoint (600 MB) downloads on first use
uv run edufidelity examples --uiclip
```

## Perturbation study

Does each measure move when, and only when, it should? Every synthetic page is degraded in
12 controlled ways (remove an element of each salience class, shift, recolor, change the
font, zoom, truncate, blank) and measured against its reference. Which measure should fall
under which perturbation was written in the code before the first run.

```bash
uv run edufidelity perturbations          # add --no-uiclip to skip the optional extra
```

The generated report is in [supplementary/perturbations](../supplementary/perturbations/README.md),
and a hand-written reading of it in [reading.md](../supplementary/perturbations/reading.md).
In short, on these synthetic pages: SSIM scores a blank page at about 0.9 and cannot tell a
missing paragraph from a missing page; UIClip reacts more to color than to missing
content; Layout Fidelity collapses under a uniform zoom; only the salience-conditioned
measures separate losing an Essential element from losing a decorative one. All 9 failed
checks were errors in the written expectations, and they are reported as such.

## Calibration (M3)

The composite score is the expected rating of a proportional-odds ordinal model, with a
ridge penalty, rescaled to 0..1. It is learned from human ratings, never weighted by
hand. Until the study's ratings exist, the procedure runs on **simulated raters** only.

```bash
uv run edufidelity calibrate --simulated                 # rehearsal, two scenarios
uv run edufidelity calibrate measures.csv ratings.csv    # ratings: generated_id,rater_id,rating
```

The procedure: hold out one educational domain; on the others, choose the ridge strength
by cross-validation with folds made of whole reference interfaces; fit; score the
held-out pages and compare with their mean human rating (Spearman and mean absolute
error). The ablation repeats it without the two salience-conditioned predictors. The
bootstrap resamples reference interfaces inside each domain and reruns everything.

The rehearsal has two simulated scenarios: one where raters care about losing Essential
and Supporting elements, and a null one where they do not. The procedure should find a
gain from salience in the first and report none in the second; the
[report](../supplementary/calibration/README.md) shows whether it does. **These are
simulations, not results.**

Checks: the unpenalized fit agrees with `statsmodels` `OrderedModel`; a very strong
penalty recovers the closed-form marginal thresholds; altering a held-out domain does not
change the model that scores it (invariant 4).

## What is not here

- **The generation pipeline.** The interfaces in the study are produced by a proprietary
  platform. This repository covers evaluation only.
- **The study corpus.** The course designs and contents belong to third parties.
- **Results.** They will be released with the paper.

## Roadmap

| Milestone | Scope |
|---|---|
| M0 (done) | Contracts, controlled rendering, collection, matching, Element Preservation, Layout Fidelity, salience-conditioned preservation, SSIM, synthetic examples, CI |
| M1 (done, except the exporter) | UIClip similarity, perturbation study, bundled fonts and a cross-system check. **Still open:** the design-file exporter to the reference format |
| M2 | Salience annotation guide, task-brief template, annotation and rating kit, inter-rater agreement |
| M3 (this version) | Ordinal calibration, leave-one-domain-out validation, ablation, clustered bootstrap, rehearsed on simulated raters |
| M4 | Frozen matching parameters from a verified development sample; supplementary material |
| M5 | Release with the paper |

Details in [docs/engineering-plan.md](engineering-plan.md).
