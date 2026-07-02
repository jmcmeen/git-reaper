"""JSON schema export for every result model.

Every JSON-emitting command publishes its schema (`--schema`) so notebooks
and models can consume reaper output without guessing. Schemas are derived
from the dataclasses in models.py; keeping them mechanical keeps them honest.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from typing import Any, Literal, Union, get_args, get_origin

from git_reaper import models

SCHEMA_VERSION = "v1"

_PRIMITIVES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _type_schema(tp: Any, defs: dict[str, Any]) -> dict[str, Any]:
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            schema = _type_schema(args[0], defs)
        else:
            schema = {"anyOf": [_type_schema(a, defs) for a in args]}
        if type(None) in get_args(tp):
            return {"anyOf": [schema, {"type": "null"}]}
        return schema
    if origin is Literal:
        return {"enum": list(get_args(tp))}
    if origin in (list, tuple):
        (item_tp, *_rest) = get_args(tp) or (str,)
        return {"type": "array", "items": _type_schema(item_tp, defs)}
    if origin is dict:
        return {"type": "object"}
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        name = tp.__name__
        if name not in defs:
            defs[name] = None  # reserve to break recursion
            defs[name] = _dataclass_schema(tp, defs)
        return {"$ref": f"#/$defs/{name}"}
    if tp in _PRIMITIVES:
        return {"type": _PRIMITIVES[tp]}
    return {}


def _dataclass_schema(cls: type, defs: dict[str, Any]) -> dict[str, Any]:
    hints = typing.get_type_hints(cls)
    properties = {f.name: _type_schema(hints[f.name], defs) for f in dataclasses.fields(cls)}
    return {
        "type": "object",
        "properties": properties,
        "required": [f.name for f in dataclasses.fields(cls)],
        "additionalProperties": False,
    }


def schema_for(cls: type) -> dict[str, Any]:
    """Build a JSON schema for a result model dataclass."""
    defs: dict[str, Any] = {}
    root = _dataclass_schema(cls, defs)
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/jmcmeen/git-reaper/schemas/{cls.__name__}/{SCHEMA_VERSION}",
        "title": cls.__name__,
        **root,
    }
    if defs:
        schema["$defs"] = defs
    return schema


#: Command name -> the model its JSON output serializes. The single registry:
#: `--schema` output, provenance schema strings, and the CLI-sync test all
#: derive from this mapping.
COMMAND_MODELS: dict[str, type] = {
    "harvest": models.HarvestResult,
    "tree": models.TreeResult,
    "conjure": models.PackResult,
    "reanimate": models.ReanimateResult,
    "census": models.CensusResult,
    "unfinished": models.UnfinishedResult,
    "grimoire": models.GrimoireResult,
    "pulse": models.PulseResult,
    "banish": models.BanishResult,
    "chronicle": models.ChronicleResult,
    "souls": models.SoulsResult,
    "haunt": models.HauntResult,
    "autopsy": models.AutopsyResult,
    "graveyard": models.GraveyardResult,
    "resurrect": models.ResurrectResult,
    "ghosts": models.GhostsResult,
    "rot": models.RotResult,
    "tombstone": models.TombstoneResult,
}

#: Commands with no JSON output of their own (`cast` emits whatever the
#: recipe's command emits), exempt from the --schema contract.
SCHEMALESS_COMMANDS = frozenset({"cast"})


def artifact_schema(command: str) -> str:
    """The provenance schema string for a command's artifacts, e.g. 'harvest/v1'."""
    if command not in COMMAND_MODELS:
        raise KeyError(f"no schema registered for command {command!r}")
    return f"{command}/{SCHEMA_VERSION}"
