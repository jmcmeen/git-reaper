"""Omens: the composite risk prophecy."""

from __future__ import annotations

import pytest

from git_reaper.config import DEFAULT_OMEN_WEIGHTS, GrimoireError, omens_weights
from git_reaper.core.risk import doomed, omens
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import render_omens
from git_reaper.gitio import GitError

#: hot.py churns in every commit (two of them bug fixes); cold.py is buried
#: once and never touched again.
SCRIPT = [
    {
        "message": "seed",
        "when": "2020-01-01T00:00:00+00:00",
        "write": {"hot.py": "a = 1\n", "cold.py": "leave me\n" * 50},
    },
    {
        "message": "fix: hot bug",
        "when": "2020-06-01T00:00:00+00:00",
        "write": {"hot.py": "a = 1\nb = 2\nc = 3\n"},
    },
    {
        "message": "fix: hot again",
        "when": "2021-01-01T00:00:00+00:00",
        "write": {"hot.py": "a = 9\nb = 2\nc = 3\nd = 4\n"},
    },
]

NOW = 1609459200.0  # 2021-01-01T00:00:00Z, pinned like every other clock here


@pytest.fixture
def prophecy(make_history):
    repo = resolve_source(str(make_history(SCRIPT))).repo
    return omens(repo, now=NOW, generated="2021-01-01T00:00:00Z")


def test_hot_files_rank_above_cold_ones(prophecy):
    ranked = [o.path for o in prophecy.omens]
    assert ranked[0] == "hot.py"
    hot, cold = prophecy.omens[0], next(o for o in prophecy.omens if o.path == "cold.py")
    assert hot.score > cold.score
    assert hot.bug_commits == 2 and cold.bug_commits == 0
    assert hot.age_days == 0 and cold.age_days == 366


def test_scores_are_normalized(prophecy):
    for omen in prophecy.omens:
        for value in (omen.score, omen.churn_score, omen.bug_score, omen.age_score):
            assert 0.0 <= value <= 1.0


def test_lens_isolates_one_component(make_history):
    repo = resolve_source(str(make_history(SCRIPT))).repo
    by_size = omens(repo, lens="size", now=NOW)
    top = by_size.omens[0]
    assert top.path == "cold.py"  # the big file wins the size lens
    assert top.score == top.size_score


def test_unknown_lens_is_refused(make_history):
    repo = resolve_source(str(make_history(SCRIPT))).repo
    with pytest.raises(ValueError):
        omens(repo, lens="tarot")


def test_dead_files_get_no_omens(make_history):
    root = make_history(
        [
            {"message": "seed", "write": {"alive.py": "x\n", "doomed.py": "y\n"}},
            {"message": "kill", "delete": ["doomed.py"]},
        ]
    )
    result = omens(resolve_source(str(root)).repo)
    assert {o.path for o in result.omens} == {"alive.py"}


def test_plain_folders_are_refused(make_dir):
    with pytest.raises(GitError):
        omens(resolve_source(str(make_dir({"a.py": "x\n"}))).repo)


def test_doomed_respects_the_threshold(prophecy):
    assert doomed(prophecy, 0.0) == prophecy.omens
    assert doomed(prophecy, 1.01) == []


def test_render_carries_the_honest_framing(prophecy):
    assert "omens are hints, not fate" in render_omens(prophecy)


# -- grimoire weights --------------------------------------------------------


def test_weights_default_when_unconfigured(tmp_path):
    assert omens_weights(tmp_path) == DEFAULT_OMEN_WEIGHTS


def test_weights_read_from_reaperrc(tmp_path):
    (tmp_path / ".reaperrc").write_text("[omens]\nchurn = 0.9\nsize = 0.1\n")
    weights = omens_weights(tmp_path)
    assert weights["churn"] == 0.9 and weights["size"] == 0.1
    assert weights["bugs"] == DEFAULT_OMEN_WEIGHTS["bugs"]


@pytest.mark.parametrize(
    "toml",
    [
        "[omens]\nvibes = 1.0\n",
        "[omens]\nchurn = -1\n",
        "[omens]\nchurn = 0.0\nbugs = 0.0\nage = 0.0\nsize = 0.0\n",
        'omens = "not a table"\n',
    ],
)
def test_miswritten_weights_are_refused(tmp_path, toml):
    (tmp_path / ".reaperrc").write_text(toml)
    with pytest.raises(GrimoireError):
        omens_weights(tmp_path)


def test_custom_weights_change_the_blend(make_history):
    repo = resolve_source(str(make_history(SCRIPT))).repo
    size_heavy = omens(repo, weights={"churn": 0, "bugs": 0, "age": 0, "size": 1}, now=NOW)
    assert size_heavy.omens[0].path == "cold.py"
