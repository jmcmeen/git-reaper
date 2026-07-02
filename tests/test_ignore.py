"""The ignore matcher, checked against real `git check-ignore` verdicts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from git_reaper.ignore import IgnoreMatcher, walk_files

RULES = "*.log\nbuild/\n!keep.log\nsecrets/**\n"

PATHS = [
    "app.log",
    "keep.log",
    "src/app.log",
    "build/out.txt",
    "builds/out.txt",
    "secrets/key.pem",
    "src/main.py",
]


def test_matcher_agrees_with_git_check_ignore(make_repo):
    root = make_repo({".gitignore": RULES, "src/main.py": "x\n"})
    matcher = IgnoreMatcher(root)
    for rel in PATHS:
        proc = subprocess.run(["git", "check-ignore", "-q", rel], cwd=root, capture_output=True)
        git_says_ignored = proc.returncode == 0
        assert matcher.ignored(rel) == git_says_ignored, rel


def test_git_dir_always_ignored(tmp_path: Path):
    matcher = IgnoreMatcher(tmp_path)
    assert matcher.ignored(".git/config")
    assert matcher.ignored(".git", is_dir=True)


def test_walk_files_deterministic_and_filtered(make_dir):
    root = make_dir(
        {
            ".gitignore": "*.log\n",
            "b.md": "b\n",
            "a.md": "a\n",
            "debug.log": "noise\n",
            "sub/c.md": "c\n",
        }
    )
    rels = [p.relative_to(root).as_posix() for p in walk_files(root, IgnoreMatcher(root))]
    assert rels == [".gitignore", "a.md", "b.md", "sub/c.md"]


def test_symlinks_never_followed(make_dir, tmp_path: Path):
    root = make_dir({"real.md": "x\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.md").write_text("leak\n")
    (root / "link").symlink_to(outside)
    rels = [p.relative_to(root).as_posix() for p in walk_files(root, IgnoreMatcher(root))]
    assert rels == ["real.md"]
