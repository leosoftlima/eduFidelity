# Engineering plan

Status: M0 implemented. Everything after M0 is a plan and may change with the paper.

## 1. Goal and non-goals

**Goal.** Given a reference design and a generated page, produce the automatic evidence
defined by the method; given human ratings, calibrate and validate the composite score.
Anyone should be able to run it on their own pages.

**Non-goals.** Generating interfaces; distributing the study corpus; reporting results
before the paper.

## 2. Invariants

Each one is a test or a CI check.

1. **The reference does not depend on the output.** Salience labels and the reference
   representation are frozen (digest) before any measurement.
2. **Nothing is dropped silently.** Generation and rendering failures are rows with a
   category.
3. **Measures stay separate.** The composite exists only after calibration.
4. **No leakage across folds.** Standardization, missing-value treatment and
   regularization are fitted on training domains only.
5. **Determinism.** Same input, configuration and seed give the same table.
6. **Frozen configuration.** Matching parameters, model checkpoint revision, browser
   version and viewport are stored with a digest in every row.
7. **Metamorphic relations.** Removing an element never increases preservation; removing
   an Essential element lowers Essential preservation; displacing an element lowers
   layout fidelity without changing preservation; an identical page scores the maximum.
8. **Missing by design.** A category without eligible elements is empty, never 0 or 1.

Covered today: 2, 3, 4 (calibration, M3), 5 (within one system and, for the example table, across systems), 7, 8.

## 3. Architecture

```
src/edufidelity/
  models.py        data contracts
  render.py        Playwright: screenshot + DOM in a fixed environment
  collector.py     in-page element collector
  matching.py      cost model + one-to-one assignment, plus a greedy baseline
  measures/        ssim, structure (EP, LF), salience
  pipeline.py      reference building (synthetic) and measurement
  examples.py      synthetic course and defect variants
  cli.py
examples/pages/    hand-authored references and the variant manifest
tests/
```

Planned: `figma.py` (design file to reference), `measures/uiclip.py`, `agreement.py`,
`calibration/`, `sampling.py`, `protocol/`, `supplementary/`.

## 4. Decisions taken in M0

| Decision | Choice | Why | Alternative rejected |
|---|---|---|---|
| Geometry normalization | Both sides normalized by the reference frame | A generated page that grows taller must not be rescaled into agreement | Normalizing each page by its own size |
| Granularity of graphics | A graphic is one leaf element | A multi-path icon is one thing to a learner | Counting every vector node |
| Text boxes | Box hugs the text, not the block | Closer to how design tools report text | Block box, which hides horizontal displacement |
| Matching | Type gate, content + spatial cost, optimal assignment, cost ceiling | Position alone fails when layout moves; content alone fails on repeated text | Greedy IoU (kept as baseline) |
| Text similarity | Character ratio rescaled above a floor | Unrelated sentences in one language still share many characters | Raw ratio, which let position outvote content |
| SSIM on different heights | Pad to a common canvas, never resize | Resizing distorts text and rewards truncated pages | Resize to the reference |
| Render readiness | Fonts, images and two equal layout signatures | A fixed sleep is either slow or wrong | Virtual time budget |
| Network | Closed during render | A render must not depend on a remote asset | Open network |

### Decisions taken in M1

| Decision | Choice | Why | Alternative rejected |
|---|---|---|---|
| UIClip checkpoint | Final checkpoint of the UIClip paper (web pairs + human pairs), pinned by revision; original CLIP processor, also pinned | It is the one the authors validated against designers' rankings | The unpinned latest revision |
| UIClip on long pages | Mean of 224 px square windows slid along the long side, as in the authors' reference code; worst band kept as a diagnostic | Same procedure the checkpoint was validated with; nothing is cropped away | Squashing the page into one square; the processor's center crop |
| UIClip dependency | Optional extra (`uiclip`); the CI runs the logic with a fake embedder | torch and a 600 MB checkpoint should not be required for the other five measures | A hard dependency |
| Fonts of the examples | DejaVu bundled under `examples/fonts/`, loaded from local files | The example table must not depend on the machine; the CI compares it on two systems | System fonts (Arial on Windows, a substitute on Linux) |
| Perturbation expectations | Which measure should fall under which perturbation is fixed in code before running; misses are reported, not edited away | Otherwise the study can only confirm itself | Writing expectations after looking at the numbers |

### Decisions taken in M4 (tools)

| Decision | Choice | Why | Alternative rejected |
|---|---|---|---|
| Verification interface | A static HTML page per generated page, images embedded, no network; the person picks, for each reference element, the same element in the generated page or "no pair" | Works offline, needs no server, leaves a JSON file per page | A spreadsheet of ids without the screenshots |
| Metric | Pair precision, recall and F1, pooled over pages | The quantity the plan says to publish | Element-level agreement only |
| Selection | Best F1 on a fixed grid; ties go to the provisional defaults | Deterministic and conservative when the sample cannot discriminate | Random or last-best tie-breaking |
| Freezing | Configuration digest, development-sample digest and timestamp in one file, verified on load; refused when the sample shares a reference with the study | "Digest recorded before any study data" | Copying numbers into the code by hand |
| Snapshot of each measurement | `measure` writes the collected elements next to the screenshot | The pairs of any measured page can be verified later | Re-rendering to verify |

### Decisions taken in M2

| Decision | Choice | Why | Alternative rejected |
|---|---|---|---|
| Agreement statistic | Own Krippendorff's alpha from the coincidence matrix; checked against the published worked example and against the `krippendorff` package | Handles missing values and ordinal data; two references | Cohen's kappa (two coders, no missing values) |
| Salience resolution | Strict majority; otherwise adjudication with a written reason; nothing is written until every element is resolved | A tie must be a recorded decision, not an accident of order | First label or random choice |
| Ordinal order of salience | Decorative < Supporting < Essential, for ordinal alpha | Disagreeing Essential/Decorative is worse than Essential/Supporting | Nominal alpha only |
| Rater groups | Each page gets the same number of raters from every group | RQ1 compares perspectives; an unbalanced design confounds rater group with page | Random raters per page |
| Annotators and raters | An annotator never rates pages of a reference they labeled | Knowing the labels biases the rating | No constraint |
| Blinding | Opaque codes, shuffled order, key kept apart | Raters must not know the model or condition | Showing generated ids |

### Decisions taken in M3

| Decision | Choice | Why | Alternative rejected |
|---|---|---|---|
| Ordinal model | Own short implementation: proportional odds, L2 on standardized coefficients, ordered thresholds by positive increments, L-BFGS-B with the analytic gradient | Small, auditable, and the penalty is not available in `statsmodels` | Depending on `mord` for the penalized model; the closed form under a strong penalty serves as the penalized reference instead |
| Checks of the model | Unpenalized fit equal to `statsmodels` `OrderedModel` within 1e-3; a very strong penalty recovers the closed-form marginal thresholds; analytic gradient equal to the numerical one | Two independent references, one of them exact | Trusting the optimizer |
| Unit of analysis | Individual ratings for fitting; the generated page (mean rating) for Spearman and MAE | Fitting uses every rating; evaluation compares one prediction per page | Fitting on rounded medians, which discards rater spread |
| Ridge selection | Grouped cross-validation on the training domains, folds made of whole reference interfaces, held-out log-loss | Pages of one reference are not independent | Ungrouped folds, which leak through near-copies |
| Preprocessing | Mean imputation and standardization inside the model, fitted on training rows only; tested by altering a held-out domain and checking that its model does not change | Invariant 4 | Standardizing the whole table once |
| Bootstrap | Reference interfaces resampled with replacement inside each domain; a repeated interface becomes a new cluster; the whole procedure reruns on every resample | Uncertainty of the procedure, not of one fitted model | Resampling ratings, which ignores clustering |
| Rehearsal data | Simulated raters with a known generating process, in two scenarios: salience matters, and a null scenario | Checks that the procedure finds a real effect and reports a null one | Waiting for human data to test the code |

## 5. Open questions

- **Q1. Layout Fidelity is brittle to reflow.** In the synthetic examples, removing a
  header logo shifts the page by a few pixels and the mean IoU of matched elements falls
  to nearly zero although nothing else changed. Options: report mean IoU as defined;
  add a shift-tolerant variant (IoU after removing the median displacement) as a
  diagnostic; or compare relative arrangement. A decision for the authors.
- **Q2. Roles in the reference.** *M1 exporter: a configurable naming rule on node and component names, with a provisional default list; the authors decide the convention.* Design tools do not carry control semantics. The
  `control` type on the reference side must come from a naming convention or manual
  annotation, and the protocol must say which.
- **Q3. UIClip on long pages.** *Partly answered in M1: the checkpoint is applied with
  its authors' sliding-window procedure, so no part of the page is cropped away. Still
  open: whether a mean over many windows dilutes a defect confined to one band of a long
  page; the synthetic pages are too short to tell.* Original note: the encoder sees 224 px. A full-page screenshot loses
  most detail. Plan: whole page as the primary measure, viewport-sized bands as a
  diagnostic, and a perturbation study to decide whether the adaptation holds.
- **Q4. Replaced text.** Text rewritten beyond the similarity floor counts as one
  missing plus one additional element. Whether partial credit is wanted is open.
- **Q5. Ordinal mixed-effects models** *(still open after M3)* have no mature Python implementation; an R script
  outside the package is the likely route.
- **Q6. Sparse rating levels.** *Treatment proposed in M3: a weak penalty on the thresholds keeps them finite, and every fit records the levels absent from its training data, reported per held-out domain. For the authors to confirm.* With few rated interfaces, a rating level may be absent
  from a training fold, leaving thresholds undetermined. Needs a stated treatment.

## 6. Milestones and acceptance

| Milestone | Scope | Acceptance |
|---|---|---|
| **M0** (done) | Contracts, render, collection, matching, EP, LF, salience preservation, SSIM, examples, CI | `edufidelity examples` produces the table; invariants 2, 3, 7, 8 green |
| **M1** (partly done: all but the exporter) | UIClip and perturbation study; bundled fonts; design-file exporter | Perturbation report; the measure drops under every destructive perturbation, or the report says where it does not; tables match across systems within tolerance |
| **M2** (done; not yet used with people) | Salience guide, brief template, annotation and rating kit, Krippendorff's alpha, blind assignment | Alpha matches published reference values; assignment reproducible by seed |
| **M3** (done on simulated raters) | Ordinal ridge calibration, leave-one-domain-out, ablation, clustered bootstrap, on simulated raters | Agrees with reference libraries; invariant 4 green |
| **M4** (done: defaults confirmed on six verified real pages) | Matching parameters frozen on a verified development sample; supplementary material | Pair precision and recall published; digest recorded before any study data |
| **M5** | Release with the paper | One command rebuilds every table of the paper from the released data |

## 7. Pre-mortem

| What could go wrong | Prevention |
|---|---|
| Matching errors propagate to every structural measure | Verified development sample; published pair precision and recall; baseline alongside |
| A reader cannot reproduce because the corpus is closed | Say so up front; complete synthetic examples; anonymized tables if permitted |
| Example numbers are read as study results | Warning in the README, the CLI docs and the example module |
| The repository stays "in progress" and looks abandoned | Small milestones, each closed with a tag |
| The salience hypothesis gives a null result | The ablation is predefined; a null result is reported as such |
