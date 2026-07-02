"""CLI: exit codes, stdout purity, aliases, --plain."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from git_reaper import __version__
from git_reaper.cli import app

runner = CliRunner()

FILES = {
    "README.md": "# top\n",
    "docs/guide.md": "read\n",
    "src/main.py": "print('hi')\n",
}


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"git-reaper {__version__}" in result.output


def test_harvest_stdout_is_artifact_only(make_repo):
    root = make_repo(FILES)
    result = runner.invoke(app, ["--plain", "harvest", str(root)])
    assert result.exit_code == 0
    assert result.stdout.startswith("<!--\ngit-reaper harvest")
    assert "## docs/guide.md" in result.stdout


def test_harvest_writes_out_file(make_repo, tmp_path):
    root = make_repo(FILES)
    out = tmp_path / "artifact.md"
    result = runner.invoke(app, ["--plain", "harvest", str(root), "--out", str(out)])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "## README.md" in out.read_text()


def test_aliases_are_gone(make_repo):
    root = make_repo(FILES)
    for command in ("reap", "map", "doctor", "purge"):
        result = runner.invoke(app, ["--plain", command, str(root)])
        assert result.exit_code == 2, command


def test_harvest_missing_source_exits_1():
    result = runner.invoke(app, ["--plain", "harvest", "/no/such/crypt"])
    assert result.exit_code == 1


def test_usage_error_exits_2():
    result = runner.invoke(app, ["harvest", ".", "--bogus-flag"])
    assert result.exit_code == 2


def test_tree_md_and_json(make_repo):
    root = make_repo(FILES)
    md = runner.invoke(app, ["--plain", "tree", str(root)])
    assert md.exit_code == 0
    assert "|-- docs/" in md.stdout

    js = runner.invoke(app, ["--plain", "tree", str(root), "--format", "json"])
    data = json.loads(js.stdout)
    assert data["provenance"]["schema"] == "tree/v1"


def test_tree_bad_format_exits_1(make_repo):
    root = make_repo(FILES)
    result = runner.invoke(app, ["--plain", "tree", str(root), "--format", "yaml"])
    assert result.exit_code == 1


def test_schema_flags_print_json():
    for command in ("harvest", "tree", "pulse", "banish"):
        result = runner.invoke(app, ["--plain", command, "--schema"])
        assert result.exit_code == 0, command
        schema = json.loads(result.stdout)
        assert schema["type"] == "object"


def test_pulse_runs():
    result = runner.invoke(app, ["--plain", "pulse", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert any(check["name"] == "git" for check in data["checks"])


def test_banish_empty_catacombs():
    result = runner.invoke(app, ["--plain", "banish"])
    assert result.exit_code == 0
