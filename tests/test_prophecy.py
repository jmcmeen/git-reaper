"""Prophecy: the forecast. Hints, not fate; deterministic under a pinned now."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import prophecy as prophecy_core
from git_reaper.models import RepoRef

runner = CliRunner()

#: "now" pinned to 2020-03-01T00:00:00Z, after every scripted commit.
NOW = 1583020800.0


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


SCRIPT = [
    # ancient, then quiet: cold.
    {"message": "seed old", "when": "2019-01-01T00:00:00+00:00", "write": {"cold.py": "v1\n"}},
    # active inside the 90-day horizon: hot, with momentum.
    {"message": "stir", "when": "2020-02-01T00:00:00+00:00", "write": {"hot.py": "v1\n"}},
    {"message": "fix the stir", "when": "2020-02-15T00:00:00+00:00", "write": {"hot.py": "v2\n"}},
]


def test_prophecy_ranks_the_heating_files_first(make_history):
    root = make_history(SCRIPT)
    result = prophecy_core.prophecy(ref(root), now=NOW)
    ranked = [p.path for p in result.prophecies]
    assert ranked[0] == "hot.py"
    hot = result.prophecies[0]
    cold = next(p for p in result.prophecies if p.path == "cold.py")
    assert hot.score > cold.score
    assert hot.recent_commits == 2 and hot.prior_commits == 0
    assert hot.momentum == 1.0
    assert hot.bug_momentum == 0.5  # one fix among two recent commits
    assert cold.recent_commits == 0
    assert cold.momentum == 0.0


def test_prophecy_scores_are_deterministic(make_history):
    root = make_history(SCRIPT)
    a = prophecy_core.prophecy(ref(root), now=NOW, generated="2020-03-01T00:00:00Z")
    b = prophecy_core.prophecy(ref(root), now=NOW, generated="2020-03-01T00:00:00Z")
    assert a == b


def test_prophecy_limit_and_horizon(make_history):
    root = make_history(SCRIPT)
    result = prophecy_core.prophecy(ref(root), limit=1, now=NOW)
    assert len(result.prophecies) == 1
    wide = prophecy_core.prophecy(ref(root), horizon_days=365 * 2, now=NOW)
    cold = next(p for p in wide.prophecies if p.path == "cold.py")
    assert cold.recent_commits == 1  # a two-year horizon reaches the old commit

    with pytest.raises(ValueError):
        prophecy_core.prophecy(ref(root), horizon_days=0, now=NOW)


def test_prophecy_only_reads_the_living(make_history):
    script = [
        *SCRIPT,
        {"message": "bury", "when": "2020-02-20T00:00:00+00:00", "delete": ["hot.py"]},
    ]
    root = make_history(script, name="buried")
    result = prophecy_core.prophecy(ref(root), now=NOW)
    assert all(p.path != "hot.py" for p in result.prophecies)


def test_prophecy_cli(make_history):
    root = make_history(SCRIPT)
    result = runner.invoke(app, ["--plain", "prophecy", str(root), "--limit", "5"])
    assert result.exit_code == 0
    assert "schema:    prophecy/v1" in result.stdout
    assert "hints, not fate" in result.stdout
