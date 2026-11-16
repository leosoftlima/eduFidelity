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

## Human evaluation kit (M2)

Everything the people in the study touch, and the code that keeps the protocol honest.
The guide and the brief template are **drafts for the authors**:
[salience guide](annotation/salience-guide.md), [task brief template](annotation/brief-template.md).

```bash
# 1. Salience: one blank sheet per annotator, plus the brief they read first
uv run edufidelity annotation-sheets reference.json --brief brief.json --annotators ana,bia
# 2. Strict majority per element; agreement; elements without a majority go to adjudication
uv run edufidelity resolve-salience reference.json annotation/page/ana.csv annotation/page/bia.csv --out labeled.json
# 3. Blind rating sheets: every page gets one rater per perspective, never an annotator of its reference
uv run edufidelity assign-ratings measures.csv raters.csv --annotators annotators.csv --seed 7
# 4. Back through the key, into the format the calibration reads
uv run edufidelity collect-ratings rating --out ratings.csv
uv run edufidelity agreement ratings.csv --level ordinal
uv run edufidelity calibrate measures.csv ratings.csv
```

- **Agreement:** Krippendorff's alpha (nominal, ordinal, interval, ratio), from the
  coincidence matrix, with missing values. It reproduces the published values of
  Krippendorff (2011) (0.743, 0.815, 0.849, 0.797) and agrees with the `krippendorff`
  package to 1e-9.
- **Salience:** a sheet is rejected if any element is blank, unknown or duplicated.
  Without a strict majority an element waits for adjudication, which must carry a written
  reason; the labeled reference is written only when every element is resolved, with its
  digest.
- **Blind assignment:** raters see opaque codes in a shuffled order; the key stays with
  the coordinator. Every page gets `--per-group` raters from each group (education,
  design, computing); annotators never rate pages of references they labeled; load is
  balanced; the seed makes it reproducible. Pages that failed to render are not sent to
  raters, and remain in the measurement table as failures.

## Reference representation from Figma

`edufidelity figma-reference` turns one frame of a Figma file (the JSON returned by the
public REST API, `GET /v1/files/:key`) into a reference representation, with the same
element rules the DOM collector applies to generated pages: visible text nodes are
text; image fills and icons drawn with vectors are graphics (one leaf each); containers
are not elements; boxes are normalized by the frame.

```bash
uv run edufidelity figma-reference file.json 12:345 --domain biology --out reference.json
```

**Controls are the open part (Q2).** Figma has no notion of a button or a link, so a
control is recognized by a naming convention on the node or on its component. The
default patterns (`button`, `botão`, `btn`, `link`, `input`, `checkbox`, `radio`, or a
name starting with `control/`) are a proposal; `--control-pattern` replaces them. The
reference screenshot is exported from Figma separately.

## Pages served by a local server

Generated interfaces that are single-page applications need a server: the page is
assembled by JavaScript from a route or a query string. `Renderer(allowed_origins=...)`
renders such a page by URL, and opens **only** the listed local origins
(`http://127.0.0.1:<port>` or `http://localhost:<port>`); every other request is still
blocked. `measure` accepts the URL in place of an HTML file.

## Content region of a reference

A design frame may draw more than the interface under evaluation, such as the learning
platform around the course content, which a generated page never contains.
`edufidelity crop-reference reference.json reference.png --region x,y,w,h` keeps only
the elements whose center lies in the region, re-expresses their boxes relative to it,
crops the screenshot (also when it was exported at 2x) and records the region in the
reference (`content_region`), which changes its digest. Generated pages are then rendered
at the region's width. The region is declared per course before annotation and
measurement. A first run on real pages is in
[supplementary/real-pages](../supplementary/real-pages/README.md).

## Matching development sample (M4)

The matching parameters are provisional until they are tuned on generated pages whose
pairs a person has checked, and then frozen. The tools for that are here; the sample of
real pages is not.

```bash
# 1. Measure a generated page; the elements found are saved next to the screenshot
uv run edufidelity measure reference.json reference.png page.html --workdir work
# 2. A self-contained review page (images embedded, no network) with the proposed pairs
uv run edufidelity review-pairs reference.json reference.png work/page.snapshot.json work/page.png --out dev/page
#    open dev/page/review.html, correct the pairs, save verified.json into dev/page
# 3. Evaluate the grid of parameters on every verified page
uv run edufidelity tune-matching dev
# 4. Freeze the best configuration; refused if the sample shares a reference with the study
uv run edufidelity freeze-matching dev --study-interfaces study.txt --out matching.frozen.json
# 5. Every study measurement uses it, and carries its digest in the row
uv run edufidelity measure reference.json reference.png page.html --config matching.frozen.json
```

Metrics are pair precision, recall and F1, pooled over pages, against the verified
pairs; the greedy IoU baseline is reported next to them. Ties are broken toward the
provisional defaults. The frozen file holds the configuration, its digest and the digest
of the development sample, and is checked against its own digest when loaded.

**A synthetic rehearsal** (`edufidelity dev-sample-synthetic`) derives the true pairs of
the perturbed synthetic pages from their authoring ids, including two defects aimed at the
matcher (two paragraphs swapped, a paragraph reworded). The result is in
[supplementary/matching](../supplementary/matching/README.md): the optimal matcher finds
every pair with the defaults, the greedy baseline misses 16%, and 39 of the 75
configurations tie. **The synthetic sample is too easy to choose parameters**, which is
exactly why M4 needs real pages verified by a person. An example of the review page is
`supplementary/matching/review-example.html` (download it and open it in a browser).

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
| M1 (done; the control rule of the Figma exporter is provisional) | UIClip similarity, perturbation study, bundled fonts and a cross-system check. **Still open:** the design-file exporter to the reference format |
| M2 (done; not yet used with people) | Salience annotation guide, task-brief template, annotation and rating kit, inter-rater agreement |
| M3 (done, on simulated raters) | Ordinal calibration, leave-one-domain-out validation, ablation, clustered bootstrap, rehearsed on simulated raters |
| M4 (done) | Matching parameters frozen on a verified development sample of six real pages (`config/matching.frozen.json`); every study measurement uses it with `--config` |
| M5 | Release with the paper |

Details in [docs/engineering-plan.md](engineering-plan.md).
