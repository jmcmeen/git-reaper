"""Fixture necropolis: throwaway repos built with real git, not mocks."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "Test Ghost",
            "GIT_AUTHOR_EMAIL": "ghost@example.com",
            "GIT_COMMITTER_NAME": "Test Ghost",
            "GIT_COMMITTER_EMAIL": "ghost@example.com",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "HOME": str(cwd),
            "PATH": "/usr/bin:/bin",
        },
    )
    return proc.stdout


@pytest.fixture
def make_repo(tmp_path: Path):
    """Build a throwaway git repo from a {relpath: content} mapping."""

    def _make(files: dict[str, str | bytes], name: str = "corpse") -> Path:
        root = tmp_path / name
        root.mkdir()
        git("init", "-b", "main", cwd=root)
        write_tree(root, files)
        git("add", "-A", cwd=root)
        git("commit", "-m", "burial", cwd=root)
        return root

    return _make


def write_tree(root: Path, files: dict[str, str | bytes]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")


@pytest.fixture
def make_dir(tmp_path: Path):
    """Build a plain (non-git) directory from a {relpath: content} mapping."""

    def _make(files: dict[str, str | bytes], name: str = "plainfolder") -> Path:
        root = tmp_path / name
        root.mkdir()
        write_tree(root, files)
        return root

    return _make


@pytest.fixture(autouse=True)
def isolated_catacombs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own cache; nobody touches ~/.cache."""
    catacombs = tmp_path / "catacombs"
    monkeypatch.setenv("GIT_REAPER_CACHE", str(catacombs))
    return catacombs
