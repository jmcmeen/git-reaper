"""Possession: the ownership map and the bus-factor hotspots."""

from __future__ import annotations

from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import possession as possession_core
from git_reaper.models import RepoRef

runner = CliRunner()

ALICE = ("Alice", "alice@example.com")
BOB = ("Bob", "bob@example.com")


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


SCRIPT = [
    {
        "message": "seed",
        "when": "2020-01-01T00:00:00+00:00",
        "author": ALICE,
        "write": {"src/core.py": "v1\n", "docs/a.md": "d1\n"},
    },
    {
        "message": "alice again",
        "when": "2020-01-02T00:00:00+00:00",
        "author": ALICE,
        "write": {"src/core.py": "v2\n"},
    },
    {
        "message": "alice a third time",
        "when": "2020-01-03T00:00:00+00:00",
        "author": ALICE,
        "write": {"src/core.py": "v3\n"},
    },
    {
        "message": "bob visits",
        "when": "2020-01-04T00:00:00+00:00",
        "author": BOB,
        "write": {"src/core.py": "v4\n", "docs/a.md": "d2\n"},
    },
    {
        "message": "kill the doc",
        "when": "2020-01-05T00:00:00+00:00",
        "author": BOB,
        "delete": ["docs/a.md"],
    },
]


def test_possession_measures_owners_and_shares(make_history):
    root = make_history(SCRIPT)
    result = possession_core.possession(ref(root))
    core = next(f for f in result.files if f.path == "src/core.py")
    assert core.owner == "Alice"
    assert core.owner_commits == 3 and core.commits == 4
    assert core.share == 0.75
    assert core.possessed  # 0.75 meets the default threshold
    assert result.possessed_count >= 1


def test_possession_ignores_the_dead(make_history):
    root = make_history(SCRIPT)
    result = possession_core.possession(ref(root))
    assert all(f.path != "docs/a.md" for f in result.files)


def test_possession_threshold_moves_the_line(make_history):
    root = make_history(SCRIPT)
    strict = possession_core.possession(ref(root), threshold=0.9)
    core = next(f for f in strict.files if f.path == "src/core.py")
    assert not core.possessed
    assert strict.threshold == 0.9


def test_possession_rolls_up_directories(make_history):
    root = make_history(SCRIPT)
    result = possession_core.possession(ref(root))
    src = next(d for d in result.dirs if d.path == "src")
    assert src.owner == "Alice"
    assert src.files == 1


def test_possession_owner_ties_break_alphabetically(make_history):
    root = make_history(
        [
            {
                "message": "a",
                "when": "2020-01-01T00:00:00+00:00",
                "author": BOB,
                "write": {"x.py": "1\n"},
            },
            {
                "message": "b",
                "when": "2020-01-02T00:00:00+00:00",
                "author": ALICE,
                "write": {"x.py": "2\n"},
            },
        ],
        name="tie",
    )
    result = possession_core.possession(ref(root))
    assert result.files[0].owner == "Alice"


def test_possession_cli(make_history):
    root = make_history(SCRIPT)
    result = runner.invoke(app, ["--plain", "possession", str(root)])
    assert result.exit_code == 0
    assert "schema:    possession/v1" in result.stdout
    assert "## territories" in result.stdout

    bad = runner.invoke(app, ["--plain", "possession", str(root), "--threshold", "3"])
    assert bad.exit_code == 1
