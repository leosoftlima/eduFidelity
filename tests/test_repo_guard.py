"""The repository guard rejects what must not reach the trunk."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repo_guard", ROOT / "scripts" / "repo_guard.py")
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_clean_text_file_passes(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("nothing to see", encoding="utf-8")
    assert guard.check([tmp_path / "notes.md"], tmp_path) == []


def test_binary_outside_allowed_folders_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "page.png").write_bytes(b"\x89PNG")
    (tmp_path / "examples" / "fonts").mkdir(parents=True)
    (tmp_path / "examples" / "fonts" / "f.ttf").write_bytes(b"\0")
    problems = guard.check(
        [tmp_path / "data" / "page.png", tmp_path / "examples" / "fonts" / "f.ttf"], tmp_path
    )
    assert len(problems) == 1 and "data/page.png" in problems[0]


def test_large_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_bytes(b"a" * (guard.MAX_BYTES + 1))
    assert "2 MB" in guard.check([tmp_path / "big.txt"], tmp_path)[0]


def test_credentials_are_rejected(tmp_path: Path) -> None:
    fake = "ghp_" + "A" * 36
    (tmp_path / "config.py").write_text(f"TOKEN = '{fake}'", encoding="utf-8")
    assert "GitHub token" in guard.check([tmp_path / "config.py"], tmp_path)[0]


def test_tracked_files_of_this_repository_pass() -> None:
    assert guard.check(guard.tracked_files(ROOT), ROOT) == []
