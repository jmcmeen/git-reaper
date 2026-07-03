"""The grimoire: config layering, recipes, and cast."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from git_reaper import config
from git_reaper.cli import app

runner = CliRunner()

REAPERRC = """
[recipes.mapit]
command = "limbs"
args = ["."]
description = "map the crypt"

[recipes.snapshot]
command = "conjure"
args = [".", "--sha256"]
"""

PYPROJECT = """
[tool.reaper.recipes.mapit]
command = "census"
args = ["."]

[tool.reaper.recipes.only-here]
command = "pulse"
args = []
"""


def test_load_grimoire_layers_and_precedence(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / ".reaperrc").write_text(REAPERRC)
    result = config.load_grimoire(tmp_path)
    recipes = {r.name: r for r in result.recipes}
    assert set(recipes) == {"mapit", "snapshot", "only-here"}
    # .reaperrc outranks pyproject for the same name
    assert recipes["mapit"].command == "limbs"
    assert recipes["mapit"].source == ".reaperrc"
    assert recipes["only-here"].source == "pyproject.toml"
    assert len(result.files) == 2


def test_grimoire_settings_report_sources(tmp_path: Path, isolated_catacombs: Path):
    result = config.load_grimoire(tmp_path)
    cache_dir = next(v for v in result.settings if v.key == "cache_dir")
    assert cache_dir.value == str(isolated_catacombs)
    assert cache_dir.source == "env GIT_REAPER_CACHE"


def test_miswritten_grimoire_is_a_plain_error(tmp_path: Path):
    (tmp_path / ".reaperrc").write_text("[recipes.broken]\nargs = [1, 2]\n")
    with pytest.raises(config.GrimoireError, match="broken"):
        config.load_grimoire(tmp_path)
    (tmp_path / ".reaperrc").write_text("not toml [ at all\n")
    with pytest.raises(config.GrimoireError, match="TOML"):
        config.load_grimoire(tmp_path)


def test_grimoire_cli_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".reaperrc").write_text(REAPERRC)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "grimoire", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert [r["name"] for r in data["recipes"]] == ["mapit", "snapshot"]


def test_cast_runs_a_recipe(make_dir, monkeypatch: pytest.MonkeyPatch):
    root = make_dir({"README.md": "# top\n"})
    (root / ".reaperrc").write_text(REAPERRC)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["--plain", "cast", "mapit"])
    assert result.exit_code == 0
    assert "README.md" in result.stdout


def test_cast_passes_overrides_through(make_dir, monkeypatch: pytest.MonkeyPatch):
    root = make_dir({"README.md": "# top\n"})
    (root / ".reaperrc").write_text(REAPERRC)
    monkeypatch.chdir(root)
    result = runner.invoke(app, ["--plain", "cast", "mapit", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["file_count"] >= 1


def test_cast_unknown_recipe_dies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "cast", "seance"])
    assert result.exit_code == 1


def test_cast_cannot_cast_cast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / ".reaperrc").write_text('[recipes.loop]\ncommand = "cast"\nargs = ["loop"]\n')
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "cast", "loop"])
    assert result.exit_code == 1


# -- writing recipes (the Grimoire chamber's save/delete) --------------------


def test_save_recipe_creates_and_round_trips(tmp_path: Path):
    recipe = config.Recipe(
        name="nightly", command="census", args=[".", "--format", "json"], description="the count"
    )
    path = config.save_recipe(recipe, root=tmp_path)
    assert path == tmp_path / ".reaperrc"
    loaded = config.find_recipe("nightly", root=tmp_path)
    assert loaded is not None
    assert loaded.command == "census"
    assert loaded.args == [".", "--format", "json"]
    assert loaded.description == "the count"


def test_save_recipe_replaces_without_touching_neighbors(tmp_path: Path):
    (tmp_path / ".reaperrc").write_text(
        '# my grimoire\n[omens]\nchurn = 0.5\n\n[recipes.old]\ncommand = "limbs"\nargs = []\n',
        encoding="utf-8",
    )
    config.save_recipe(config.Recipe(name="old", command="census", args=["."]), root=tmp_path)
    text = (tmp_path / ".reaperrc").read_text(encoding="utf-8")
    assert "# my grimoire" in text  # comments outside the section survive
    assert "churn = 0.5" in text
    assert text.count("[recipes.old]") == 1
    loaded = config.find_recipe("old", root=tmp_path)
    assert loaded is not None and loaded.command == "census"


def test_delete_recipe_strikes_only_its_section(tmp_path: Path):
    config.save_recipe(config.Recipe(name="one", command="limbs", args=[]), root=tmp_path)
    config.save_recipe(config.Recipe(name="two", command="census", args=[]), root=tmp_path)
    config.delete_recipe("one", root=tmp_path)
    assert config.find_recipe("one", root=tmp_path) is None
    assert config.find_recipe("two", root=tmp_path) is not None


def test_delete_pyproject_recipe_points_at_the_file(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.reaper.recipes.inscribed]\ncommand = "limbs"\nargs = []\n', encoding="utf-8"
    )
    with pytest.raises(config.GrimoireError, match=r"pyproject\.toml"):
        config.delete_recipe("inscribed", root=tmp_path)


def test_save_recipe_refuses_nameless_and_commandless(tmp_path: Path):
    with pytest.raises(config.GrimoireError, match="needs a name"):
        config.save_recipe(config.Recipe(name=" ", command="census", args=[]), root=tmp_path)
    with pytest.raises(config.GrimoireError, match="needs a command"):
        config.save_recipe(config.Recipe(name="x", command="", args=[]), root=tmp_path)


def test_save_recipe_quotes_odd_names_and_args(tmp_path: Path):
    recipe = config.Recipe(name="spooky pack", command="conjure", args=["--out", 'a "b".md'])
    config.save_recipe(recipe, root=tmp_path)
    loaded = config.find_recipe("spooky pack", root=tmp_path)
    assert loaded is not None
    assert loaded.args == ["--out", 'a "b".md']
    config.delete_recipe("spooky pack", root=tmp_path)
    assert config.find_recipe("spooky pack", root=tmp_path) is None
