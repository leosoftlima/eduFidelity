"""Run every quality gate locally, in the same order as CI. Stops at the first failure.

uv run python scripts/check.py            # everything
uv run python scripts/check.py --fast     # without the browser tests
"""

from __future__ import annotations

import subprocess
import sys

FAST = "--fast" in sys.argv
STEPS: list[tuple[str, list[str]]] = [
    ("repository guard", [sys.executable, "scripts/repo_guard.py"]),
    ("lint", ["ruff", "check", "."]),
    ("format", ["ruff", "format", "--check", "."]),
    ("types", ["mypy", "src"]),
    (
        "tests",
        [
            "pytest",
            "-q",
            "-m",
            "not uiclip and not browser" if FAST else "not uiclip",
            "--cov=edufidelity",
            "--cov-report=term-missing:skip-covered",
            # without the browser tests the coverage floor does not apply
            *(["--cov-fail-under=0"] if FAST else []),
        ],
    ),
]


def main() -> int:
    for name, command in STEPS:
        print(f"\n== {name}: {' '.join(command)}", flush=True)
        if subprocess.run(command).returncode != 0:
            print(f"\nFAILED: {name}")
            return 1
    print("\nAll gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
