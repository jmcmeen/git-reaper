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

#: Default blend for the omens prophecy; override via [omens] in the grimoire.
DEFAULT_OMEN_WEIGHTS: dict[str, float] = {"churn": 0.35, "bugs": 0.30, "age": 0.20, "size": 0.15}


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

    layers = _layered_tables(root)
    weights = omens_weights(root)
    weights_source = next(
        (source for source, table in reversed(layers) if table.get("omens")), "default"
    )
    result.settings.append(
        ConfigValue(
            key="omens_weights",
            value=" ".join(f"{k}={weights[k]:g}" for k in sorted(weights)),
            source=weights_source,
        )
    )
    rules = custom_rules(root)
    rules_source = next(
        (source for source, table in reversed(layers) if table.get("rules")), "default"
    )
    result.settings.append(
        ConfigValue(
            key="custom_rules",
            value=", ".join(sorted(rules)) if rules else "none",
            source=rules_source if rules else "default",
        )
    )

    result.recipes = sorted(recipes.values(), key=lambda r: r.name)
    return result


def find_recipe(name: str, root: Path | None = None) -> Recipe | None:
    for recipe in load_grimoire(root).recipes:
        if recipe.name == name:
            return recipe
    return None


def _layered_tables(root: Path | None = None) -> list[tuple[str, dict[str, Any]]]:
    """Grimoire tables weakest-first: pyproject [tool.reaper], then .reaperrc."""
    root = root or Path.cwd()
    layers: list[tuple[str, dict[str, Any]]] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        table = _load_toml(pyproject).get("tool", {}).get("reaper", {})
        if isinstance(table, dict) and table:
            layers.append(("pyproject.toml", table))
    reaperrc = root / CONFIG_FILE
    if reaperrc.is_file():
        layers.append((CONFIG_FILE, _load_toml(reaperrc)))
    return layers


def custom_rules(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """[rules.<name>] tables for the shared exhume/veil engine.

    .reaperrc outranks pyproject; validation of each rule's fields happens in
    rules.load_rules, which owns what a rule means.
    """
    merged: dict[str, dict[str, Any]] = {}
    for source, table in _layered_tables(root):
        rules = table.get("rules", {})
        if not isinstance(rules, dict):
            raise GrimoireError(f"{source}: 'rules' must be a table of rule tables")
        for name, spec in rules.items():
            if not isinstance(spec, dict):
                raise GrimoireError(f"{source}: rule {name!r} must be a table")
            merged[name] = spec
    return merged


def omens_weights(root: Path | None = None) -> dict[str, float]:
    """The [omens] weight blend, defaults filled in for missing keys."""
    weights = dict(DEFAULT_OMEN_WEIGHTS)
    for source, table in _layered_tables(root):
        omens = table.get("omens", {})
        if not isinstance(omens, dict):
            raise GrimoireError(f"{source}: 'omens' must be a table of weights")
        for key, value in omens.items():
            if key not in DEFAULT_OMEN_WEIGHTS:
                allowed = ", ".join(sorted(DEFAULT_OMEN_WEIGHTS))
                raise GrimoireError(f"{source}: unknown omens weight {key!r} (use {allowed})")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise GrimoireError(f"{source}: omens weight {key!r} must be a number >= 0")
            weights[key] = float(value)
    if sum(weights.values()) <= 0:
        raise GrimoireError("omens weights must not all be zero")
    return weights
