"""CLI: exit codes, stdout purity, aliases, --plain."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from git_reaper import __version__, schemas
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
    assert data["provenance"]["schema"] == schemas.artifact_schema("tree")


def test_bad_format_exits_1(make_repo):
    root = make_repo(FILES)
    tree = runner.invoke(app, ["--plain", "tree", str(root), "--format", "yaml"])
    assert tree.exit_code == 1
    pulse = runner.invoke(app, ["--plain", "pulse", "--format", "yaml"])
    assert pulse.exit_code == 1


def test_every_visible_command_publishes_a_schema():
    # COMMAND_MODELS is the single registry; a new or renamed command must
    # register there, and every registered command must answer --schema.
    visible = {cmd.name for cmd in app.registered_commands if not cmd.hidden}
    assert visible - schemas.SCHEMALESS_COMMANDS == set(schemas.COMMAND_MODELS)
    for command in sorted(schemas.COMMAND_MODELS):
        result = runner.invoke(app, ["--plain", command, "--schema"])
        assert result.exit_code == 0, command
        schema = json.loads(result.stdout)
        assert schema["type"] == "object"


def test_boo_is_wired():
    result = runner.invoke(app, ["boo"])
    assert result.exit_code == 0


def test_conjure_reanimate_cli_round_trip(make_repo, tmp_path):
    root = make_repo(FILES)
    artifact = tmp_path / "packed.md"
    packed = runner.invoke(
        app, ["--plain", "conjure", str(root), "--sha256", "--out", str(artifact)]
    )
    assert packed.exit_code == 0

    dst = tmp_path / "risen"
    raised = runner.invoke(
        app, ["--plain", "reanimate", str(artifact), "--out", str(dst), "--verify"]
    )
    assert raised.exit_code == 0
    for rel, content in FILES.items():
        assert (dst / rel).read_text() == content


def test_conjure_split_writes_parts(make_repo, tmp_path):
    root = make_repo({f"f{i}.md": f"words {i}\n" * 100 for i in range(4)})
    out = tmp_path / "packed.md"
    result = runner.invoke(
        app, ["--plain", "conjure", str(root), "--split-tokens", "300", "--out", str(out)]
    )
    assert result.exit_code == 0
    parts = sorted(tmp_path.glob("packed.part*.md"))
    assert len(parts) > 1
    assert not out.exists()  # sharded runs write only numbered parts


def test_census_cli_formats(make_repo):
    root = make_repo(FILES)
    md = runner.invoke(app, ["--plain", "census", str(root)])
    assert md.exit_code == 0
    assert "| .md |" in md.stdout
    csv_out = runner.invoke(app, ["--plain", "census", str(root), "--format", "csv"])
    assert csv_out.stdout.startswith("extension,language,")


def test_unfinished_cli(make_repo):
    root = make_repo({"main.py": "# TODO: haunt later\n"})
    result = runner.invoke(app, ["--plain", "unfinished", str(root), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["counts"] == {"TODO": 1}
    assert data["markers"][0]["author"] == "Test Ghost"


def test_pulse_runs():
    result = runner.invoke(app, ["--plain", "pulse", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert any(check["name"] == "git" for check in data["checks"])


def test_banish_empty_catacombs():
    result = runner.invoke(app, ["--plain", "banish"])
    assert result.exit_code == 0
