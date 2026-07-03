"""The grimoire: layered configuration and named recipes.

Precedence, weakest first: built-in defaults, ``[tool.reaper]`` in
pyproject.toml, ``.reaperrc`` (TOML), environment variables. `grimoire`
shows every effective value and where it came from; `cast` runs recipes.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
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


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


def _is_bool(value: Any) -> bool:
    return type(value) is bool  # a bare isinstance would also admit 0 and 1


#: [commune] keys a grimoire may set, each with its shape check and a name
#: for the error message when the check fails.
_COMMUNE_KEYS: dict[str, tuple[Callable[[Any], bool], str]] = {
    "roots": (_is_str_list, "a list of strings"),
    "hosts": (_is_str_list, "a list of strings"),
    "tools": (_is_str_list, "a list of strings"),
    "allow_write": (_is_bool, "a boolean"),
    "allow_network": (_is_bool, "a boolean"),
    "http": (_is_str, "a string"),
}


def commune_settings(root: Path | None = None) -> dict[str, Any]:
    """The [commune] table: defaults for the MCP server, .reaperrc outranking
    pyproject. Values are validated for shape here; commune owns the meaning."""
    merged: dict[str, Any] = {}
    for source, table in _layered_tables(root):
        commune = table.get("commune", {})
        if not isinstance(commune, dict):
            raise GrimoireError(f"{source}: 'commune' must be a table")
        for key, value in commune.items():
            if key not in _COMMUNE_KEYS:
                allowed = ", ".join(sorted(_COMMUNE_KEYS))
                raise GrimoireError(f"{source}: unknown commune key {key!r} (use {allowed})")
            check, wants = _COMMUNE_KEYS[key]
            if not check(value):
                raise GrimoireError(f"{source}: commune key {key!r} must be {wants}")
            merged[key] = value
    return merged


# --------------------------------------------------------------------------
# writing recipes -- the Grimoire chamber's save/delete, shared with any caller
# --------------------------------------------------------------------------


def _toml_string(value: str) -> str:
    """A TOML basic string. JSON escaping is a valid subset, so borrow it."""
    return json.dumps(value)


def _recipe_section(recipe: Recipe) -> str:
    """The [recipes.<name>] table for one recipe, ready to append."""
    lines = [f"[recipes.{_toml_key(recipe.name)}]"]
    lines.append(f"command = {_toml_string(recipe.command)}")
    lines.append(f"args = [{', '.join(_toml_string(a) for a in recipe.args)}]")
    if recipe.description:
        lines.append(f"description = {_toml_string(recipe.description)}")
    return "\n".join(lines) + "\n"


def _toml_key(name: str) -> str:
    """A bare key when possible, a quoted one otherwise."""
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else _toml_string(name)


def _strip_recipe_section(text: str, name: str) -> str:
    """Remove one [recipes.<name>] table, leaving everything else untouched.

    Line-based surgery on the section's own lines only, so comments and
    formatting elsewhere in the grimoire survive a save or delete.
    """
    header = re.compile(
        rf"^\[recipes\.({re.escape(name)}|\"{re.escape(name)}\"|'{re.escape(name)}')\]\s*$"
    )
    any_header = re.compile(r"^\s*\[")
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if skipping and any_header.match(line):
            skipping = False
        if not skipping and header.match(line.strip()):
            skipping = True
        if not skipping:
            out.append(line)
    # drop a trailing blank the removed section may have left behind
    return "".join(out)


def save_recipe(recipe: Recipe, root: Path | None = None) -> Path:
    """Inscribe (or re-inscribe) a recipe in .reaperrc; returns the file written.

    Only .reaperrc is ever written -- recipes living in pyproject.toml are
    edited there by hand. Because .reaperrc outranks pyproject, saving here
    also overrides a same-named pyproject recipe, which is the precedence a
    reader of `grimoire` already expects.
    """
    if not recipe.name.strip():
        raise GrimoireError("a recipe needs a name")
    if not recipe.command.strip():
        raise GrimoireError(f"recipe {recipe.name!r} needs a command")
    root = root or Path.cwd()
    path = root / CONFIG_FILE
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if text:
        _load_toml(path)  # refuse to edit a miswritten grimoire
        text = _strip_recipe_section(text, recipe.name)
        if text and not text.endswith("\n"):
            text += "\n"
        if text:
            text += "\n"
    path.write_text(text + _recipe_section(recipe), encoding="utf-8")
    return path


def delete_recipe(name: str, root: Path | None = None) -> Path:
    """Strike a recipe from .reaperrc; returns the file written.

    A recipe inscribed in pyproject.toml cannot be deleted here -- the error
    says where to edit instead of silently doing nothing.
    """
    root = root or Path.cwd()
    path = root / CONFIG_FILE
    recipe = find_recipe(name, root)
    if recipe is None:
        raise GrimoireError(f"no recipe named {name!r}")
    if recipe.source != CONFIG_FILE:
        raise GrimoireError(f"recipe {name!r} is inscribed in {recipe.source}; edit it there")
    text = path.read_text(encoding="utf-8")
    path.write_text(_strip_recipe_section(text, name), encoding="utf-8")
    return path
