"""Fixture necropolis: throwaway repos built with real git, not mocks."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest


def git(
    *args: str,
    cwd: Path,
    author: tuple[str, str] | None = None,
    when: str | None = None,
) -> str:
    """Run git in a hermetic environment.

    `author` overrides the (name, email); `when` pins both author and committer
    dates so history commands stay deterministic across machines and clocks.
    """
    name, email = author or ("Test Ghost", "ghost@example.com")
    env = {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "HOME": str(cwd),
        "PATH": "/usr/bin:/bin",
    }
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=env,
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


@dataclass
class Commit:
    """One scripted commit for the history fixture.

    Dates are pinned so every Phase 3 command that reads or computes on commit
    time stays deterministic. `branch` forks from the current HEAD the first
    time it is seen, then continues it; default stays on main.
    """

    message: str = "commit"
    when: str = "2020-01-01T00:00:00"
    author: tuple[str, str] | None = None
    write: dict[str, str | bytes] = field(default_factory=dict)
    delete: list[str] = field(default_factory=list)
    rename: dict[str, str] = field(default_factory=dict)  # old -> new
    tag: str | None = None
    branch: str = "main"


@pytest.fixture
def make_history(tmp_path: Path):
    """Build a repo by playing a list of Commit specs with pinned dates."""

    def _make(commits: list[Commit | dict], name: str = "necropolis") -> Path:
        root = tmp_path / name
        root.mkdir()
        git("init", "-b", "main", cwd=root)
        seen_branches = {"main"}
        current = "main"  # unborn until the first commit; don't check it out
        for spec in commits:
            c = Commit(**spec) if isinstance(spec, dict) else spec
            if c.branch not in seen_branches:
                git("checkout", "-b", c.branch, cwd=root)
                seen_branches.add(c.branch)
            elif c.branch != current:
                git("checkout", c.branch, cwd=root)
            current = c.branch
            write_tree(root, c.write)
            for old, new in c.rename.items():
                (root / new).parent.mkdir(parents=True, exist_ok=True)
                git("mv", old, new, cwd=root)
            for path in c.delete:
                git("rm", "-q", path, cwd=root)
            git("add", "-A", cwd=root)
            git("commit", "-m", c.message, cwd=root, author=c.author, when=c.when)
            if c.tag:
                git("tag", c.tag, cwd=root)
        git("checkout", "main", cwd=root)
        return root

    return _make


ALICE = ("Alice", "alice@example.com")
BOB = ("Bob", "bob@example.com")
CAROL = ("Carol", "carol@example.com")

#: A canonical history exercising every Phase 3 corner: multiple authors,
#: pinned dates (heatmap/age/witching-hour), a rename (autopsy --follow), a
#: deletion (graveyard/resurrect), a tag (changelog), a multiline body
#: (adversarial parser), and an unmerged branch (ghosts).
NECROPOLIS_SCRIPT = [
    {
        "message": "seed",
        "when": "2020-01-06T02:00:00+00:00",  # Mon 02:00
        "author": ALICE,
        "write": {"README.md": "# hi\n", "src/core.py": "x = 1\n"},
    },
    {
        "message": "grow core",
        "when": "2020-01-06T02:30:00+00:00",  # Mon 02:00 again -> the peak cell
        "author": ALICE,
        "write": {"src/core.py": "x = 1\ny = 2\n"},
    },
    {
        "message": "add doc",
        "when": "2020-01-08T14:00:00+00:00",  # Wed 14:00
        "author": BOB,
        "write": {"docs/old.md": "temp\n"},
    },
    {
        "message": "rename doc\n\nlong body line\nsecond body line",
        "when": "2020-01-09T02:00:00+00:00",  # Thu 02:00
        "author": BOB,
        "rename": {"docs/old.md": "docs/new.md"},
    },
    {
        "message": "kill core",
        "when": "2020-01-10T02:00:00+00:00",  # Fri 02:00
        "author": ALICE,
        "delete": ["src/core.py"],
        "write": {"src/main.py": "print()\n"},
        "tag": "v1.0.0",
    },
    {
        "message": "wip",
        "when": "2020-02-01T02:00:00+00:00",
        "author": CAROL,
        "write": {"feature.py": "f\n"},
        "branch": "feature",  # never merged into main
    },
]


@pytest.fixture
def necropolis(make_history):
    """The canonical rich history, built once per test that asks for it."""
    return make_history(NECROPOLIS_SCRIPT)


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
