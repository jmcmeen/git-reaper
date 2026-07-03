"""Wake: the changelog draft since the last tag."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import wake as wake_core
from git_reaper.gitio import GitError
from git_reaper.models import RepoRef

runner = CliRunner()


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


RELEASED_THEN_MORE = [
    {"message": "feat: seed", "when": "2020-01-01T00:00:00+00:00", "write": {"a.py": "a\n"}},
    {
        "message": "fix: patch the seed",
        "when": "2020-01-02T00:00:00+00:00",
        "write": {"a.py": "aa\n"},
        "tag": "v1.0.0",
    },
    {"message": "feat: grow limbs", "when": "2020-01-03T00:00:00+00:00", "write": {"b.py": "b\n"}},
    {
        "message": "fix(core): stop the rot",
        "when": "2020-01-04T00:00:00+00:00",
        "write": {"a.py": "a3\n"},
    },
    {"message": "tidy the crypt", "when": "2020-01-05T00:00:00+00:00", "write": {"c.md": "c\n"}},
]


def test_wake_counts_from_the_last_tag(make_history):
    root = make_history(RELEASED_THEN_MORE)
    result = wake_core.wake(ref(root))
    assert result.since == "v1.0.0"
    assert result.commits == 3
    titles = {s.title: [e.message for e in s.entries] for s in result.sections}
    assert titles["Added"] == ["feat: grow limbs"]
    assert titles["Fixed"] == ["fix(core): stop the rot"]
    assert titles["Changed"] == ["tidy the crypt"]


def test_wake_suggests_a_bump(make_history):
    root = make_history(RELEASED_THEN_MORE)
    assert wake_core.wake(ref(root)).suggested_bump == "minor"  # a feat landed

    fixes_only = make_history(
        [
            {
                "message": "seed",
                "when": "2020-01-01T00:00:00+00:00",
                "write": {"a.py": "a\n"},
                "tag": "v1",
            },
            {"message": "fix: leak", "when": "2020-01-02T00:00:00+00:00", "write": {"a.py": "b\n"}},
        ],
        name="fixes",
    )
    assert wake_core.wake(ref(fixes_only)).suggested_bump == "patch"

    breaking = make_history(
        [
            {
                "message": "seed",
                "when": "2020-01-01T00:00:00+00:00",
                "write": {"a.py": "a\n"},
                "tag": "v1",
            },
            {
                "message": "feat!: new spine",
                "when": "2020-01-02T00:00:00+00:00",
                "write": {"a.py": "b\n"},
            },
        ],
        name="breaking",
    )
    assert wake_core.wake(ref(breaking)).suggested_bump == "major"


def test_wake_without_tags_covers_the_whole_history(make_history):
    root = make_history(
        [{"message": "feat: first", "when": "2020-01-01T00:00:00+00:00", "write": {"a.py": "a\n"}}],
        name="untagged",
    )
    result = wake_core.wake(ref(root))
    assert result.since == ""
    assert result.commits == 1


def test_wake_since_overrides_the_tag(make_history):
    root = make_history(RELEASED_THEN_MORE)
    result = wake_core.wake(ref(root), since="HEAD~1")
    assert result.since == "HEAD~1"
    assert result.commits == 1


def test_wake_unknown_since_is_a_git_error(make_history):
    root = make_history(RELEASED_THEN_MORE)
    with pytest.raises(GitError):
        wake_core.wake(ref(root), since="no-such-ref")


def test_wake_nothing_new_after_the_tag(necropolis):
    # necropolis tags v1.0.0 on the newest main commit; the wake is quiet.
    result = wake_core.wake(ref(necropolis))
    assert result.commits == 0
    assert result.sections == []
    assert result.suggested_bump == "none"


def test_wake_cli_draft(make_history):
    root = make_history(RELEASED_THEN_MORE)
    result = runner.invoke(app, ["--plain", "wake", str(root)])
    assert result.exit_code == 0
    assert "schema:    wake/v1" in result.stdout
    assert "## [Unreleased]" in result.stdout
    assert "### Added" in result.stdout
    assert "a draft from `reaper wake`" in result.stdout
