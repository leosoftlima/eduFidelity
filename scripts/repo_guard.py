"""Repository guard: checks every tracked file before it can reach the trunk.

* No file above 2 MB.
* Binary files (images, fonts, archives, documents) only in the folders allowed to hold
  them; anywhere else they are probably material that must stay local.
* No credentials or private keys in text files.

Usage: ``python scripts/repo_guard.py`` (checks ``git ls-files``) or with explicit paths.
Exit code 1 on any violation.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".pdf",
    ".zip",
    ".gz",
    ".7z",
    ".rar",
    ".fig",
    ".psd",
    ".sketch",
    ".mp4",
    ".mov",
    ".safetensors",
    ".pt",
    ".bin",
}
#: Where binaries may live, as glob patterns relative to the repository root.
BINARY_ALLOWED = ("examples/fonts/*", "supplementary/*/*.png", "docs/images/*")
SECRETS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "OpenAI or Anthropic key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{32,}\b"),
}


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [root / p for p in out.stdout.decode("utf-8").split("\0") if p]


def check(paths: list[Path], root: Path) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if size > MAX_BYTES:
            problems.append(f"{rel}: {size / 1e6:.1f} MB, above the 2 MB limit")
        if path.suffix.lower() in BINARY_SUFFIXES:
            if not any(fnmatch.fnmatch(rel, pattern) for pattern in BINARY_ALLOWED):
                problems.append(f"{rel}: binary file outside the allowed folders")
            continue
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRETS.items():
            if pattern.search(text):
                problems.append(f"{rel}: looks like a {name}")
    return problems


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    paths = [Path(p).resolve() for p in argv] if argv else tracked_files(root)
    problems = check(paths, root)
    for problem in problems:
        print(f"guard: {problem}")
    print(f"guard: {len(paths)} files checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
