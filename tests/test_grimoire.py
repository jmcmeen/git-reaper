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
command = "tree"
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
    assert recipes["mapit"].command == "tree"
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
