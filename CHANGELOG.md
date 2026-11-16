# Changelog

All notable changes to this repository. Format: [Keep a Changelog](https://keepachangelog.com/);
versions: [Semantic Versioning](https://semver.org/), major 0 until the paper is out.

## [Unreleased]

### Governance
- Branch model, pull request rules, methodological-change policy and data rules (`CONTRIBUTING.md`).
- CI split into guard, lint and format, strict types, and tests on Linux and Windows with
  Python 3.11 and 3.12; coverage floor of 84%; actions pinned by commit.
- Repository guard (size, binary locations, credentials), pre-commit hooks, one local
  command for every gate (`scripts/check.py`), code owners, templates, Dependabot.
- Trunk protection ruleset and repository settings, applied by the owner with
  `scripts/apply-repo-settings.sh`.

### M4 · Matching frozen
- Verification of pairs by hand on a self-contained review page; pair precision, recall
  and F1; grid tuning; freezing with digests, refused on overlap with the study.
- `config/matching.frozen.json`, confirmed on six verified real pages (content area only).
- Content region of a reference frame (`crop-reference`); rendering of pages served by a
  local server with the network otherwise closed.

### M2 · Human evaluation kit
- Krippendorff's alpha (nominal, ordinal, interval, ratio), checked against published values.
- Salience annotation sheets, majority resolution and adjudication; blind rating
  assignment by rater group; collection into the calibration format.
- Drafts of the salience guide and the task-brief template.

### M3 · Calibration
- Ordinal ridge regression checked against `statsmodels`; leave-one-domain-out
  validation; ablation of 6 against 4 predictors; clustered bootstrap; rehearsal on
  simulated raters.

### M1 · UIClip, perturbations, Figma
- UIClip similarity (optional extra, pinned checkpoint, sliding windows).
- Perturbation study with expectations fixed before running.
- Bundled fonts and a cross-system check of the example table.
- Reference representation from the public Figma file format.

### M0 · Evaluation toolkit
- Data contracts, controlled rendering, element collection, matching, Element
  Preservation, Layout Fidelity, salience-conditioned preservation, SSIM, synthetic examples.
