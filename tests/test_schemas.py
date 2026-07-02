"""Schema export: every JSON output validates against its published schema."""

from __future__ import annotations

from git_reaper import schemas
from git_reaper.core.source import resolve_source
from git_reaper.core.tree import tree
from git_reaper.formatters import jsonfmt
from git_reaper.models import HarvestResult, TreeResult


def test_every_command_has_a_schema():
    for command, model in schemas.COMMAND_MODELS.items():
        schema = schemas.schema_for(model)
        assert schema["title"] == model.__name__, command
        assert schema["type"] == "object"
        assert "properties" in schema


def test_nested_dataclasses_become_refs():
    schema = schemas.schema_for(HarvestResult)
    assert "Provenance" in schema["$defs"]
    assert "FileEntry" in schema["$defs"]


def test_recursive_model_does_not_explode():
    schema = schemas.schema_for(TreeResult)
    assert "TreeNode" in schema["$defs"]
    node = schema["$defs"]["TreeNode"]
    assert node["properties"]["children"]["items"] == {"$ref": "#/$defs/TreeNode"}


def test_tree_json_matches_schema_shape(make_dir):
    import json

    result = tree(resolve_source(str(make_dir({"a.md": "x\n"}))).repo)
    data = json.loads(jsonfmt.render(result))
    schema = schemas.schema_for(TreeResult)
    assert set(data.keys()) == set(schema["properties"].keys())
