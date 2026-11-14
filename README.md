# EduFidelity

**Salience-Aware, Human-Calibrated Evaluation of LLM-Generated E-Learning Interfaces in Instructional Design Workflows**

EduFidelity is a research framework for assessing how faithfully large language models (LLMs) transform **Figma reference designs** into implemented **e-learning interfaces**. It examines whether generated interfaces preserve not just visual appearance, but also structural organization and the instructional importance of interface elements.

The framework integrates technical measurements and human judgments to support evaluation in instructional-design workflows. The evaluation is organized into four research questions (RQs), with separate data-collection and analysis stages.

> **Repository status:** Research and replication package in preparation. The public repository is intended to contain reproducible inputs, data schemas, evaluation scripts, and documentation. Internal DidacticGen implementation details are not part of the public release.

## Implementation status

A first part of the evaluation toolkit is in the repository. It is **work in progress**,
and **nothing it produces today is a result of the study**: the only numbers it can
compute come from small synthetic pages written to test the pipeline.

| Part of the framework | Status |
| --- | --- |
| Data contracts (reference representation, rendered DOM, correspondences, measurement rows) | Implemented as typed models |
| Controlled rendering of a generated page (fixed browser, viewport, no animations, stable-state wait; failures recorded, never dropped) | Implemented |
| Element collection from the rendered DOM | Implemented |
| One-to-one matching between reference and rendered elements | Implemented, **parameters provisional** (not yet tuned on a verified development sample) |
| Element Preservation, Layout Fidelity (RQ2) | Implemented |
| SSIM (RQ2) | Implemented |
| UIClip (RQ2) | Planned |
| Preservation by salience category (RQ3) | Implemented (computation only; no annotation protocol yet) |
| Human evaluation kit and inter-rater agreement (RQ1) | Planned |
| Ordinal calibration, leave-one-domain-out validation, ablation (RQ4) | Planned |
| Reference representation from Figma | Planned |

To run the synthetic examples (Python 3.11+ and [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run playwright install chromium
uv run edufidelity examples
uv run pytest
```

Details, the example table, design decisions and open methodological questions:
[docs/toolkit.md](docs/toolkit.md) and [docs/engineering-plan.md](docs/engineering-plan.md).

## Research questions

| RQ | Focus | Main evidence |
| --- | --- | --- |
| **RQ1: Human-perceived fidelity** | How do evaluators perceive the fidelity of LLM-generated interfaces to their reference designs? | Blinded human ratings from Education/Pedagogy, Design, and Computing perspectives. |
| **RQ2: Computational fidelity** | How faithfully do generated interfaces preserve visual and structural characteristics? | SSIM, UIClip, Element Preservation, and Layout Fidelity. |
| **RQ3: Pedagogical salience** | To what extent are instructionally important elements preserved? | Element annotations as Essential, Supporting, or Decorative, and preservation analysis by category. |
| **RQ4: Human-calibrated integration** | Can visual, structural, and pedagogical signals be combined to better align with human judgments and generalize across domains? | Ordinal calibration, leave-one-domain-out validation, correlation/error measures, and ablation analyses. |

## Evaluation framework

EduFidelity evaluates three complementary dimensions:

1. **Visual fidelity:** Structural Similarity Index Measure (**SSIM**) and **UIClip** compare the reference and generated interface renderings.
2. **Structural fidelity:** **Element Preservation** and **Layout Fidelity** assess corresponding interface elements and their arrangement through matching between the Figma-derived **Reference Design Representation (RDR)** and the rendered **Document Object Model (DOM)**.
3. **Pedagogical salience:** Reference elements are labeled **Essential**, **Supporting**, or **Decorative** according to their instructional relevance. Category-specific preservation is then analyzed; Decorative elements are reported descriptively rather than treated as an equal core calibration signal.

**Human calibration** is the integration and validation stage, **not** a fourth fidelity dimension. The combined EduFidelity model is calibrated with human judgments and evaluated for cross-domain generalization.

### High-level workflow

```text
Figma reference designs
         |
         v
Reference design representation (RDR)
         |
         +---------------------------+
         |                           |
         v                           v
LLM-based implementation      Pedagogical annotations
(via DidacticGen workflow)     (Essential / Supporting / Decorative)
         |
         v
Generated interface + rendered DOM + screenshots
         |
         +---------------------------+
         |                           |
         v                           v
Visual and structural         Blinded human evaluation
metrics (RQ2)                 (RQ1)
         |                           |
         +--------------+------------+
                        |
                        v
           Salience analysis (RQ3)
                        |
                        v
     Human-calibrated integration (RQ4)
                        |
                        v
   Cross-domain validation and analyses
```

## Experimental materials

The planned study uses a corpus of Figma-based e-learning reference pages spanning multiple instructional domains, with repeated LLM generation runs. Each output is linked to a stable `generation_id`, so human ratings, technical metrics, and pedagogical annotations can be joined without disclosing internal generation infrastructure.

The public replication package is designed to provide **the inputs and outputs necessary to understand and reproduce the evaluation**, while keeping the DidacticGen generation platform abstracted. Actual corpus counts, participating models, and completed sample sizes will be documented in the released dataset and associated paper.

## Planned repository organization

The structure below describes the intended public package. Directories and files will be added as materials are prepared.

```text
edufidelity/
├── README.md
├── docs/
│   ├── RQ1-human-evaluation.md
│   ├── RQ2-computational-fidelity.md
│   ├── RQ3-pedagogical-salience.md
│   └── RQ4-human-calibration.md
├── schemas/
│   ├── generations.schema.md
│   ├── human_ratings.schema.md
│   ├── technical_metrics.schema.md
│   └── salience_annotations.schema.md
├── inputs/
│   └── README.md
├── scripts/
│   └── README.md
├── data/
│   └── README.md
└── results/
    └── README.md
```

This is a **proposed layout**, not a claim that these files are already available. What exists today is the Python package in `src/edufidelity/`, the synthetic examples in `examples/` and the tests in `tests/`; the two will be reconciled as materials are prepared.

## Data contracts

The core CSV artifacts are intended to use explicit keys and documented column names:

| File | Purpose | Key fields (illustrative) |
| --- | --- | --- |
| `generations.csv` | Index reference pages and generated implementations. | `generation_id`, `reference_id`, `domain`, `model_id`, `run_id` |
| `human_ratings.csv` | Store blinded evaluator judgments. | `generation_id`, `evaluator_id`, `evaluator_group`, `rating` |
| `technical_metrics.csv` | Store visual and structural results. | `generation_id`, `ssim`, `uiclip`, `element_preservation`, `layout_fidelity` |
| `salience_annotations.csv` | Link reference elements to instructional-importance labels and preservation outcomes. | `reference_id`, `element_id`, `salience_category`, `preserved` |

The exact scales, units, matching rules, exclusion criteria, missing-value conventions, and final column schemas will be specified alongside the released scripts. Do not interpret the illustrative fields above as a finalized data specification.

## Reproduction overview

1. **Prepare the references.** Freeze eligible reference designs, identifiers, annotations, and export settings.
2. **Generate the interfaces.** Execute the documented generation protocol with repeated runs. Export public-safe artifacts such as screenshots, rendered DOM or HTML snapshots, and generation metadata; assign each output a unique `generation_id`.
3. **Collect human judgments (RQ1).** Perform blinded evaluation and export judgments to `human_ratings.csv`.
4. **Compute technical metrics (RQ2).** Compare each generated interface with its reference using SSIM, UIClip, Element Preservation, and Layout Fidelity; export `technical_metrics.csv`.
5. **Analyze pedagogical salience (RQ3).** Annotate the instructional relevance of reference elements and compute preservation outcomes by salience category.
6. **Calibrate and validate (RQ4).** Fit the specified human-calibrated ordinal model and conduct leave-one-domain-out (LODO) evaluation, comparisons against standalone signals, and ablation studies.

**Note:** Reproduction scripts, execution commands, dependency versions, and downloadable artifacts for the study should only be added once publicly released and verified. The commands under *Implementation status* run the toolkit on synthetic examples only; they do not reproduce any study result.

## Reproducibility and responsible release

- Preserve stable identifiers across datasets and evaluations.
- Document model settings, run counts, prompt and generation protocol versions, and any exclusions.
- Separate training domains from held-out domains during leave-one-domain-out evaluation.
- Release de-identified human rating data, subject to consent and applicable approvals.
- Exclude credentials, personal information, proprietary source code, and private DidacticGen components.
- Identify any third-party design assets whose redistribution is restricted.

## Paper and citation

The companion manuscript is currently being prepared. Bibliographic metadata and a BibTeX citation will be added when available. Until then, please refer to this repository by its project name, **EduFidelity**, and its published repository URL once assigned.

## License

**To be defined.** Code, datasets, and third-party design assets may require distinct licenses. No usage rights beyond those stated in subsequently published license files are implied by this README.

## Contact and contributions

Contribution guidelines, maintainers, and issue-tracking conventions will be documented when the public replication package is released.
