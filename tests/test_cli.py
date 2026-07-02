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


# -- git necromancy (Phase 3) ----------------------------------------------


def test_chronicle_cli_formats(necropolis):
    md = runner.invoke(app, ["--plain", "chronicle", str(necropolis)])
    assert md.exit_code == 0
    assert md.stdout.startswith("<!--\ngit-reaper chronicle")
    assert "| sha |" in md.stdout

    js = runner.invoke(app, ["--plain", "chronicle", str(necropolis), "--format", "json"])
    data = json.loads(js.stdout)
    assert data["provenance"]["schema"] == schemas.artifact_schema("chronicle")
    assert len(data["commits"]) == 5

    csv_out = runner.invoke(app, ["--plain", "chronicle", str(necropolis), "--format", "csv"])
    assert csv_out.stdout.startswith("sha,date,author,")


def test_chronicle_changelog_cli(necropolis):
    result = runner.invoke(app, ["--plain", "chronicle", str(necropolis), "--changelog"])
    assert result.exit_code == 0
    assert "## v1.0.0" in result.stdout


def test_souls_heatmap_cli(necropolis):
    result = runner.invoke(app, ["--plain", "souls", str(necropolis), "--heatmap"])
    assert result.exit_code == 0
    assert "activity" in result.stdout
    assert "Mon" in result.stdout


def test_haunt_cli(necropolis):
    result = runner.invoke(app, ["--plain", "haunt", str(necropolis), "--format", "json"])
    data = json.loads(result.stdout)
    assert data["hotspots"][0]["path"] == "src/core.py"


def test_autopsy_cli(necropolis):
    result = runner.invoke(
        app, ["--plain", "autopsy", "docs/new.md", "-s", str(necropolis), "--format", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "docs/old.md" in data["former_names"]


def test_autopsy_missing_arg_exits_1():
    result = runner.invoke(app, ["--plain", "autopsy"])
    assert result.exit_code == 1


def test_graveyard_and_resurrect_cli(necropolis, tmp_path):
    graves = runner.invoke(app, ["--plain", "graveyard", str(necropolis), "--format", "json"])
    dead = {d["path"] for d in json.loads(graves.stdout)["dead"]}
    assert "src/core.py" in dead

    dst = tmp_path / "risen"
    raised = runner.invoke(
        app, ["--plain", "resurrect", "src/core.py", "-s", str(necropolis), "-o", str(dst)]
    )
    assert raised.exit_code == 0
    assert (dst / "src/core.py").read_text() == "x = 1\ny = 2\n"


def test_resurrect_unknown_exits_1(necropolis, tmp_path):
    result = runner.invoke(
        app, ["--plain", "resurrect", "no/such.py", "-s", str(necropolis), "-o", str(tmp_path)]
    )
    assert result.exit_code == 1


def test_ghosts_cli(necropolis):
    result = runner.invoke(
        app, ["--plain", "ghosts", str(necropolis), "--than", "40d", "--format", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["threshold_days"] == 40
    assert {b["name"] for b in data["branches"]} == {"main", "feature"}


def test_rot_cli(necropolis):
    result = runner.invoke(app, ["--plain", "rot", str(necropolis), "--format", "json"])
    data = json.loads(result.stdout)
    assert data["files"][0]["path"] == "README.md"


def test_tombstone_cli(necropolis):
    result = runner.invoke(app, ["--plain", "tombstone", str(necropolis)])
    assert result.exit_code == 0
    assert "R I P" in result.stdout
    assert "kill core" in result.stdout


def test_history_on_plain_folder_exits_1(make_dir):
    folder = make_dir({"a.txt": "hi\n"})
    result = runner.invoke(app, ["--plain", "chronicle", str(folder)])
    assert result.exit_code == 1


def test_summon_without_the_extra_errors_clearly(monkeypatch):
    # Simulate textual being absent regardless of the local env: `reaper summon`
    # must exit 1 with the missing-extra guidance, never a raw ImportError.
    import builtins
    import sys

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "textual" or name.startswith("textual."):
            raise ImportError("no textual")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "git_reaper.tui", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = runner.invoke(app, ["--plain", "summon", "."])
    assert result.exit_code == 1


def test_history_writes_pure_artifact_to_out(necropolis, tmp_path):
    out = tmp_path / "log.md"
    result = runner.invoke(app, ["--plain", "chronicle", str(necropolis), "--out", str(out)])
    assert result.exit_code == 0
    assert result.stdout == ""  # narration went to stderr; artifact to the file
    assert "git-reaper chronicle" in out.read_text()
