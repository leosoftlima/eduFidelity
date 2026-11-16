# Contributing to EduFidelity

This repository accompanies a research paper. Every number it produces may end up in a
table of that paper, so the rules below protect two things at once: the code, and the
methodological integrity of the study. They apply to the authors as much as to anyone.

## 1. Branches

| Branch | Purpose | Lifetime |
|---|---|---|
| `leosoftlima` (default, the trunk) | Always releasable: CI green, docs consistent with the code | Permanent |
| `feat/<topic>` | New capability | Merged and deleted |
| `fix/<topic>` | Bug fix | Merged and deleted |
| `docs/<topic>` | Documentation only | Merged and deleted |
| `method/<topic>` | A change that can alter a measure, the matching, the calibration or the protocol (see §4) | Merged and deleted |
| `exp/<topic>` | Exploration that may never be merged | Deleted when done |
| `release/vX.Y` | Only if a release needs a fix after the trunk moved on | Until the paper is out |

- **Nobody pushes to the trunk.** Every change arrives through a pull request.
- Branches are short-lived: open the pull request early, as a draft if needed.
- **Stacked pull requests** are allowed for dependent work. Merge them strictly in order,
  bottom first, and retarget the next one to the trunk after each merge.
- Delete the branch after merging.

## 2. Pull requests

A pull request is merged only when:

1. **CI is green** on every job: repository guard, lint and format, strict typing, and the
   tests on Linux and Windows with the coverage floor.
2. **One approving review from a code owner other than the author** (see
   `.github/CODEOWNERS`). New commits after an approval require a new approval.
3. Every review conversation is resolved.
4. The template is filled in honestly, including what was *not* tested.

Merge method: **squash** for a single pull request, so the trunk gets one commit per
change with the pull request title as its message; **merge commit** for a stack, to keep
the order of the stacked commits. Rebase merging is disabled.

Titles follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat: …`, `fix: …`, `docs: …`, `method: …`, `test: …`, `ci: …`, `refactor: …`, `chore: …`.

## 3. Quality gates

All of them run locally with one command, and in CI on every push:

```bash
uv run python scripts/check.py          # guard, ruff, format, mypy, tests with coverage
uv run pre-commit install               # optional: the fast gates before every commit
```

| Gate | Rule |
|---|---|
| Repository guard (`scripts/repo_guard.py`) | No file above 2 MB; images and other binaries only in the folders that may hold them; no credentials or private keys |
| Lint | `ruff check` with the configured rules |
| Format | `ruff format --check` |
| Types | `mypy --strict` on `src/` |
| Tests | `pytest` on Linux and Windows, Python 3.11 and 3.12, browser tests included |
| Coverage | At least 84% of `src/` (the floor only goes up) |

A test that fails intermittently is a bug: fix it or remove it in the same pull request
that notices it, never by re-running until it passes.

## 4. Methodological changes

Anything that can change a number the paper reports is a **methodological change**:
the element rules of the collector or of the Figma exporter, the matching cost or its
frozen parameters, a measure, the content region of a course, the calibration procedure,
the agreement statistic, the annotation guide or the brief template.

Such a change:

- goes in a `method/` branch and its title starts with `method:`;
- adds a row to the decisions table of `docs/engineering-plan.md` (choice, why,
  alternative rejected);
- states in the pull request which existing results it invalidates;
- never edits `config/matching.frozen.json` by hand: a new frozen file comes from
  `edufidelity freeze-matching` on a verified development sample, **before** any study
  data is measured with it;
- once study data exists, is approved by both authors.

Expectations, thresholds and test sets fixed before a run are never edited after seeing
the results; a wrong expectation is reported as such (see
`supplementary/perturbations/reading.md`).

## 5. Data

- **No material from the study corpus or from the generation platform** (pages,
  screenshots, design files, texts of the courses) is committed. Real pages are
  measured locally; only derived numbers may be published, with opaque identifiers.
- Synthetic examples are fictitious and say so.
- Generated outputs (`examples/_build/`, `_work/`) are never committed.

## 6. Releases

Versions follow [Semantic Versioning](https://semver.org/); every release has an entry in
`CHANGELOG.md` and a tag `vX.Y.Z` on the trunk. While the paper is in preparation the
major version stays at 0. The release that accompanies the paper rebuilds every table
from the released data with one command (milestone M5).

## 7. Security

See [SECURITY.md](SECURITY.md). Never put credentials in the repository, in an issue or in
a pull request.
