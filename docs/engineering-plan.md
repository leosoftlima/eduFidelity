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

Covered today: 2, 3, 5 (within one system), 7, 8.

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

## 5. Open questions

- **Q1. Layout Fidelity is brittle to reflow.** In the synthetic examples, removing a
  header logo shifts the page by a few pixels and the mean IoU of matched elements falls
  to nearly zero although nothing else changed. Options: report mean IoU as defined;
  add a shift-tolerant variant (IoU after removing the median displacement) as a
  diagnostic; or compare relative arrangement. A decision for the authors.
- **Q2. Roles in the reference.** Design tools do not carry control semantics. The
  `control` type on the reference side must come from a naming convention or manual
  annotation, and the protocol must say which.
- **Q3. UIClip on long pages.** The encoder sees 224 px. A full-page screenshot loses
  most detail. Plan: whole page as the primary measure, viewport-sized bands as a
  diagnostic, and a perturbation study to decide whether the adaptation holds.
- **Q4. Replaced text.** Text rewritten beyond the similarity floor counts as one
  missing plus one additional element. Whether partial credit is wanted is open.
- **Q5. Ordinal mixed-effects models** have no mature Python implementation; an R script
  outside the package is the likely route.
- **Q6. Sparse rating levels.** With few rated interfaces, a rating level may be absent
  from a training fold, leaving thresholds undetermined. Needs a stated treatment.

## 6. Milestones and acceptance

| Milestone | Scope | Acceptance |
|---|---|---|
| **M0** (done) | Contracts, render, collection, matching, EP, LF, salience preservation, SSIM, examples, CI | `edufidelity examples` produces the table; invariants 2, 3, 7, 8 green |
| **M1** | UIClip and perturbation study; bundled fonts; design-file exporter | Perturbation report; the measure drops under every destructive perturbation, or the report says where it does not; tables match across systems within tolerance |
| **M2** | Salience guide, brief template, annotation and rating kit, Krippendorff's alpha, blind assignment | Alpha matches published reference values; assignment reproducible by seed |
| **M3** | Ordinal ridge calibration, leave-one-domain-out, ablation, clustered bootstrap, on simulated raters | Agrees with reference libraries; invariant 4 green |
| **M4** | Matching parameters frozen on a verified development sample; supplementary material | Pair precision and recall published; digest recorded before any study data |
| **M5** | Release with the paper | One command rebuilds every table of the paper from the released data |

## 7. Pre-mortem

| What could go wrong | Prevention |
|---|---|
| Matching errors propagate to every structural measure | Verified development sample; published pair precision and recall; baseline alongside |
| A reader cannot reproduce because the corpus is closed | Say so up front; complete synthetic examples; anonymized tables if permitted |
| Example numbers are read as study results | Warning in the README, the CLI docs and the example module |
| The repository stays "in progress" and looks abandoned | Small milestones, each closed with a tag |
| The salience hypothesis gives a null result | The ablation is predefined; a null result is reported as such |
