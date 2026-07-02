"""Tree: hierarchy, depth limits, ignore rules, formats."""

from __future__ import annotations

from git_reaper.core.source import resolve_source
from git_reaper.core.tree import tree
from git_reaper.formatters import jsonfmt
from git_reaper.formatters.markdown import render_tree

FILES = {
    "README.md": "# top\n",
    "src/pkg/deep.py": "x = 1\n",
    "src/main.py": "print('hi')\n",
    "docs/guide.md": "read\n",
}


def test_tree_structure_sorted_dirs_first(make_dir):
    result = tree(resolve_source(str(make_dir(FILES))).repo)
    names = [c.name for c in result.root.children]
    assert names == ["docs", "src", "README.md"]
    assert result.dir_count == 3
    assert result.file_count == 4


def test_tree_depth_limit(make_dir):
    result = tree(resolve_source(str(make_dir(FILES))).repo, max_depth=1)
    src = next(c for c in result.root.children if c.name == "src")
    assert src.children == []


def test_tree_dirs_only(make_dir):
    result = tree(resolve_source(str(make_dir(FILES))).repo, dirs_only=True)
    assert result.file_count == 0
    assert result.dir_count == 3


def test_tree_honors_ignore(make_dir):
    files = dict(FILES, **{".gitignore": "docs/\n", "node_modules/junk.js": "x\n"})
    result = tree(resolve_source(str(make_dir(files))).repo, excludes=["node_modules/"])
    names = [c.name for c in result.root.children]
    assert "docs" not in names
    assert "node_modules" not in names


def test_render_tree_ascii(make_dir):
    result = tree(resolve_source(str(make_dir(FILES))).repo, with_sizes=True, with_lines=True)
    text = render_tree(result, with_sizes=True, with_lines=True)
    assert "|-- docs/" in text
    assert "`-- README.md" in text
    assert "3 directories, 4 files" in text


def test_tree_json_round_trips(make_dir):
    import json

    result = tree(resolve_source(str(make_dir(FILES))).repo, generated="2026-07-01T00:00:00Z")
    data = json.loads(jsonfmt.render(result))
    assert data["provenance"]["schema"] == "tree/v1"
    assert data["root"]["is_dir"] is True
