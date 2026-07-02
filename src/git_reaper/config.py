"""The grimoire: layered configuration and named recipes.

Precedence, weakest first: built-in defaults, ``[tool.reaper]`` in
pyproject.toml, ``.reaperrc`` (TOML), environment variables. `grimoire`
shows every effective value and where it came from; `cast` runs recipes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from git_reaper import cache
from git_reaper.models import ConfigValue, GrimoireResult, Recipe

CONFIG_FILE = ".reaperrc"


class GrimoireError(ValueError):
    """The grimoire is miswritten. Message names the file and the sin."""


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data: dict[str, Any] = tomllib.load(fh)
            return data
    except tomllib.TOMLDecodeError as exc:
        raise GrimoireError(f"{path} is not valid TOML: {exc}") from exc


def _parse_recipes(table: Any, source: str) -> list[Recipe]:
    if not isinstance(table, dict):
        raise GrimoireError(f"{source}: 'recipes' must be a table of recipe tables")
    recipes = []
    for name, spec in table.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("command"), str):
            raise GrimoireError(f"{source}: recipe {name!r} needs a string 'command'")
        args = spec.get("args", [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise GrimoireError(f"{source}: recipe {name!r} 'args' must be a list of strings")
        recipes.append(
            Recipe(
                name=name,
                command=spec["command"],
                args=list(args),
                description=str(spec.get("description", "")),
                source=source,
            )
        )
    return recipes


def load_grimoire(root: Path | None = None) -> GrimoireResult:
    """Read every config source under root (default: cwd) and merge."""
    root = root or Path.cwd()
    result = GrimoireResult()
    recipes: dict[str, Recipe] = {}

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        table = _load_toml(pyproject).get("tool", {}).get("reaper", {})
        if table:
            result.files.append(str(pyproject))
            for recipe in _parse_recipes(table.get("recipes", {}), "pyproject.toml"):
                recipes[recipe.name] = recipe

    reaperrc = root / CONFIG_FILE
    if reaperrc.is_file():
        result.files.append(str(reaperrc))
        table = _load_toml(reaperrc)
        for recipe in _parse_recipes(table.get("recipes", {}), CONFIG_FILE):
            recipes[recipe.name] = recipe  # .reaperrc outranks pyproject

    cache_env = os.environ.get("GIT_REAPER_CACHE")
    result.settings.append(
        ConfigValue(
            key="cache_dir",
            value=str(cache.catacombs_root()),
            source="env GIT_REAPER_CACHE" if cache_env else "default",
        )
    )
    no_color = os.environ.get("NO_COLOR")
    result.settings.append(
        ConfigValue(
            key="color",
            value="disabled" if no_color else "auto",
            source="env NO_COLOR" if no_color else "default",
        )
    )

    result.recipes = sorted(recipes.values(), key=lambda r: r.name)
    return result


def find_recipe(name: str, root: Path | None = None) -> Recipe | None:
    for recipe in load_grimoire(root).recipes:
        if recipe.name == name:
            return recipe
    return None
