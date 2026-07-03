"""Lineage: the pickaxe, and who first summoned a line."""

from __future__ import annotations

from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import lineage as lineage_core
from git_reaper.models import RepoRef

runner = CliRunner()


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


SCRIPT = [
    {
        "message": "summon the token",
        "when": "2020-01-01T00:00:00+00:00",
        "write": {"src/a.py": "MAGIC_TOKEN = 1\n"},
    },
    {
        "message": "unrelated work",
        "when": "2020-01-02T00:00:00+00:00",
        "write": {"docs/b.md": "notes\n"},
    },
    {
        "message": "banish the token",
        "when": "2020-01-03T00:00:00+00:00",
        "write": {"src/a.py": "x = 1\n"},
    },
]


def test_lineage_finds_origin_and_every_touch(make_history):
    root = make_history(SCRIPT)
    result = lineage_core.lineage(ref(root), "MAGIC_TOKEN")
    messages = [c.message for c in result.commits]
    assert messages == ["banish the token", "summon the token"]  # newest first
    assert result.origin is not None
    assert result.origin.message == "summon the token"


def test_lineage_misses_honestly(make_history):
    root = make_history(SCRIPT)
    result = lineage_core.lineage(ref(root), "NEVER_WRITTEN")
    assert result.commits == []
    assert result.origin is None


def test_lineage_regex_mode(make_history):
    root = make_history(SCRIPT)
    result = lineage_core.lineage(ref(root), r"MAGIC_\w+", regex=True)
    assert result.regex
    assert [c.message for c in result.commits] == ["banish the token", "summon the token"]


def test_lineage_path_filter(make_history):
    root = make_history(SCRIPT)
    result = lineage_core.lineage(ref(root), "MAGIC_TOKEN", rel_path="docs")
    assert result.commits == []
    assert result.path == "docs"


def test_lineage_cli(make_history):
    root = make_history(SCRIPT)
    result = runner.invoke(app, ["--plain", "lineage", "MAGIC_TOKEN", "--source", str(root)])
    assert result.exit_code == 0
    assert "schema:    lineage/v1" in result.stdout
    assert "first summoned by" in result.stdout

    missing = runner.invoke(app, ["--plain", "lineage"])
    assert missing.exit_code == 1
