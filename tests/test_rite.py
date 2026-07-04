"""Rites: multi-step recipes stored in the grimoire, run across sources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from git_reaper import config, rite
from git_reaper.cli import app
from git_reaper.models import Rite, RiteStep

runner = CliRunner()

REAPERRC = """
[[rites.audit.steps]]
command = "chronicle"
args = ["--changelog"]

[[rites.audit.steps]]
command = "census"
name = "loc"
"""

PYPROJECT = """
[tool.reaper.rites.audit]
description = "shadowed by .reaperrc"

[[tool.reaper.rites.audit.steps]]
command = "limbs"

[tool.reaper.rites.only-here]

[[tool.reaper.rites.only-here.steps]]
command = "omens"
"""


def test_load_rites_from_reaperrc_and_pyproject_precedence(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / ".reaperrc").write_text(REAPERRC)
    result = config.load_grimoire(tmp_path)
    rites = {r.name: r for r in result.rites}
    assert set(rites) == {"audit", "only-here"}
    # .reaperrc outranks pyproject for the same name
    assert [s.command for s in rites["audit"].steps] == ["chronicle", "census"]
    assert rites["audit"].source == ".reaperrc"
    assert rites["only-here"].source == "pyproject.toml"
    assert rites["audit"].steps[1].name == "loc"


def test_rite_needs_at_least_one_step(tmp_path: Path):
    (tmp_path / ".reaperrc").write_text("[rites.empty]\nsteps = []\n")
    with pytest.raises(config.GrimoireError, match="at least one step"):
        config.load_grimoire(tmp_path)


def test_rite_step_needs_a_command(tmp_path: Path):
    (tmp_path / ".reaperrc").write_text('[[rites.broken.steps]]\nname = "x"\n')
    with pytest.raises(config.GrimoireError, match="needs a string 'command'"):
        config.load_grimoire(tmp_path)


def test_find_rite_returns_none_when_absent(tmp_path: Path):
    assert config.find_rite("nope", root=tmp_path) is None


def test_perform_rite_runs_steps_in_order_and_combines(make_repo):
    root = make_repo({"README.md": "# top\n"})
    a_rite = Rite(
        name="audit",
        steps=[
            RiteStep(command="chronicle", args=["{source}"]),
            RiteStep(command="census", args=["{source}"], name="loc"),
        ],
    )
    result = rite.perform_rite(a_rite, [str(root)])
    assert result.ok
    assert [o.step for o in result.outcomes] == ["chronicle", "loc"]
    combined = result.combined()
    assert set(combined[str(root)]) == {"chronicle", "loc"}
    assert combined[str(root)]["chronicle"]["commits"][0]["message"] == "burial"


def test_perform_rite_across_multiple_sources(make_repo):
    root_a = make_repo({"a.py": "print('a')\n"}, name="corpse-a")
    root_b = make_repo({"b.py": "print('b')\n"}, name="corpse-b")
    a_rite = Rite(name="census-all", steps=[RiteStep(command="census", args=["{source}"])])
    result = rite.perform_rite(a_rite, [str(root_a), str(root_b)])
    assert result.ok
    assert result.sources == [str(root_a), str(root_b)]
    combined = result.combined()
    assert set(combined) == {str(root_a), str(root_b)}


def test_perform_rite_defaults_to_cwd_when_no_sources(make_repo, monkeypatch: pytest.MonkeyPatch):
    root = make_repo({"README.md": "# top\n"})
    monkeypatch.chdir(root)
    a_rite = Rite(name="here", steps=[RiteStep(command="census")])
    result = rite.perform_rite(a_rite)
    assert result.sources == ["."]
    assert result.ok


def test_perform_rite_rejects_ineligible_command():
    a_rite = Rite(name="bad", steps=[RiteStep(command="summon")])
    with pytest.raises(rite.RiteError, match="cannot combine output"):
        rite.perform_rite(a_rite, ["."])


def test_perform_rite_requires_at_least_one_step():
    with pytest.raises(rite.RiteError, match="no steps"):
        rite.perform_rite(Rite(name="empty", steps=[]), ["."])


# -- writing rites (the Coven chamber's save/delete) -------------------------


def test_save_rite_creates_and_round_trips(tmp_path: Path):
    a_rite = Rite(
        name="nightly",
        steps=[
            RiteStep(command="chronicle", args=["{source}", "--changelog"]),
            RiteStep(command="census", args=["{source}"], name="loc"),
        ],
        description="the nightly sweep",
    )
    path = config.save_rite(a_rite, root=tmp_path)
    assert path == tmp_path / ".reaperrc"
    loaded = config.find_rite("nightly", root=tmp_path)
    assert loaded is not None
    assert loaded.description == "the nightly sweep"
    assert [s.command for s in loaded.steps] == ["chronicle", "census"]
    assert loaded.steps[0].args == ["{source}", "--changelog"]
    assert loaded.steps[1].name == "loc"


def test_save_rite_replaces_without_touching_neighbors(tmp_path: Path):
    (tmp_path / ".reaperrc").write_text(
        "# my grimoire\n[omens]\nchurn = 0.5\n\n"
        '[rites.old]\n\n[[rites.old.steps]]\ncommand = "limbs"\n',
        encoding="utf-8",
    )
    config.save_rite(
        Rite(name="old", steps=[RiteStep(command="census")]),
        root=tmp_path,
    )
    text = (tmp_path / ".reaperrc").read_text(encoding="utf-8")
    assert "# my grimoire" in text
    assert "churn = 0.5" in text
    assert text.count("[rites.old]") == 1
    assert text.count("[[rites.old.steps]]") == 1
    loaded = config.find_rite("old", root=tmp_path)
    assert loaded is not None and loaded.steps[0].command == "census"


def test_delete_rite_strikes_only_its_section(tmp_path: Path):
    config.save_rite(Rite(name="one", steps=[RiteStep(command="limbs")]), root=tmp_path)
    config.save_rite(Rite(name="two", steps=[RiteStep(command="census")]), root=tmp_path)
    config.delete_rite("one", root=tmp_path)
    assert config.find_rite("one", root=tmp_path) is None
    assert config.find_rite("two", root=tmp_path) is not None


def test_delete_pyproject_rite_points_at_the_file(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.reaper.rites.inscribed]\n\n"
        '[[tool.reaper.rites.inscribed.steps]]\ncommand = "limbs"\n',
        encoding="utf-8",
    )
    with pytest.raises(config.GrimoireError, match=r"pyproject\.toml"):
        config.delete_rite("inscribed", root=tmp_path)


def test_save_rite_refuses_nameless_stepless_and_commandless(tmp_path: Path):
    with pytest.raises(config.GrimoireError, match="needs a name"):
        config.save_rite(Rite(name=" ", steps=[RiteStep(command="census")]), root=tmp_path)
    with pytest.raises(config.GrimoireError, match="at least one step"):
        config.save_rite(Rite(name="x", steps=[]), root=tmp_path)
    with pytest.raises(config.GrimoireError, match="no command"):
        config.save_rite(Rite(name="x", steps=[RiteStep(command="")]), root=tmp_path)


def test_save_rite_quotes_odd_names_and_args(tmp_path: Path):
    a_rite = Rite(
        name="spooky rite", steps=[RiteStep(command="conjure", args=["--out", 'a "b".md'])]
    )
    config.save_rite(a_rite, root=tmp_path)
    loaded = config.find_rite("spooky rite", root=tmp_path)
    assert loaded is not None
    assert loaded.steps[0].args == ["--out", 'a "b".md']
    config.delete_rite("spooky rite", root=tmp_path)
    assert config.find_rite("spooky rite", root=tmp_path) is None


def test_perform_rite_records_failure_without_aborting(make_repo):
    root = make_repo({"README.md": "# top\n"})
    a_rite = Rite(
        name="mixed",
        steps=[
            RiteStep(command="chronicle", args=["{source}"]),
            RiteStep(command="lineage"),  # no needle given -> dies
        ],
    )
    result = rite.perform_rite(a_rite, [str(root)])
    assert not result.ok
    chronicle_outcome, lineage_outcome = result.outcomes
    assert chronicle_outcome.ok
    assert not lineage_outcome.ok
    assert lineage_outcome.error
    combined = result.combined()
    assert combined[str(root)]["lineage"] == {"error": lineage_outcome.error}


# -- the `perform` CLI verb ---------------------------------------------------

PERFORM_RC = """
[[rites.audit.steps]]
command = "chronicle"
args = ["{source}", "--changelog"]

[[rites.audit.steps]]
command = "census"
name = "loc"
args = ["{source}"]
"""


def test_perform_runs_a_rite(make_repo, monkeypatch: pytest.MonkeyPatch):
    root = make_repo({"README.md": "# top\n"})
    (root / ".reaperrc").write_text(PERFORM_RC)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["--plain", "perform", "audit", "."])
    assert result.exit_code == 0
    assert "chronicle" in result.stdout
    assert "loc" in result.stdout


def test_perform_json_combines_every_step(make_repo, monkeypatch: pytest.MonkeyPatch):
    root = make_repo({"README.md": "# top\n"})
    (root / ".reaperrc").write_text(PERFORM_RC)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["--plain", "perform", "audit", ".", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert {o["step"] for o in data["outcomes"]} == {"chronicle", "loc"}


def test_perform_unknown_rite_dies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "perform", "seance"])
    assert result.exit_code == 1


def test_perform_no_rite_given_dies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "perform"])
    assert result.exit_code == 1


def test_perform_schema_needs_no_rite_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "perform", "--schema"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["title"] == "RiteResult"


def test_perform_exits_nonzero_on_step_failure(make_repo, monkeypatch: pytest.MonkeyPatch):
    root = make_repo({"README.md": "# top\n"})
    (root / ".reaperrc").write_text(
        '[[rites.broken.steps]]\ncommand = "lineage"\n'  # no needle -> dies
    )
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["--plain", "perform", "broken", "."])
    assert result.exit_code == 1
