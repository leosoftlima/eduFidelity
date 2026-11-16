## What changes

<!-- One or two sentences. Link the issue or the milestone. -->

## Kind of change

- [ ] Code, no effect on any reported number
- [ ] **Methodological** (`method:`): can change a measure, the matching, the calibration or the protocol — see CONTRIBUTING §4
- [ ] Documentation only

## Methodological changes only

- [ ] Row added to the decisions table of `docs/engineering-plan.md`
- [ ] Results this invalidates are listed below
- [ ] `config/matching.frozen.json` untouched, or regenerated with `freeze-matching` before any study data

## Checks

- [ ] `uv run python scripts/check.py` passes locally
- [ ] Nothing from the study corpus or the generation platform is added (pages, screenshots, design files, course texts)
- [ ] Documentation matches the code

## Not tested

<!-- What this change was not tested on, and why. "Nothing" is a valid answer only if true. -->
