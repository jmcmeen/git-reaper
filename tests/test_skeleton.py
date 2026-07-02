"""Bones: the code map."""

from __future__ import annotations

import pytest

from git_reaper.core.skeleton import bones
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import render_bones

PY_MODULE = '''"""Module doc."""

import os
from pathlib import Path


class Reaper(Tool):
    """Holds the scythe."""

    def reap(self, souls: int = 1) -> int:
        """Collect."""
        return souls


async def summon(name: str) -> None:
    await rituals.begin(name)
'''


def _bones(make_dir, files):
    return bones(resolve_source(str(make_dir(files))).repo)


def test_python_structure_is_kept(make_dir):
    result = _bones(make_dir, {"reaper.py": PY_MODULE})
    (file,) = result.files
    assert file.parsed and file.language == "python"
    by_name = {e.name: e for e in file.entries}
    assert by_name["os"].kind == "import"
    assert by_name["pathlib"].signature == "from pathlib import Path"
    assert by_name["Reaper"].signature == "class Reaper(Tool)"
    assert by_name["Reaper"].doc == "Holds the scythe."
    assert by_name["reap"].kind == "method" and by_name["reap"].depth == 1
    assert by_name["reap"].signature == "def reap(self, souls: int=1) -> int"
    assert by_name["summon"].kind == "function"
    assert by_name["summon"].signature.startswith("async def summon")


def test_implementation_is_stripped(make_dir):
    result = _bones(make_dir, {"reaper.py": PY_MODULE})
    text = render_bones(result)
    assert "class Reaper(Tool)" in text
    assert "return souls" not in text  # the flesh is gone


def test_syntax_errors_are_reported_not_fatal(make_dir):
    result = _bones(make_dir, {"broken.py": "def nope(:\n", "fine.py": "def ok(): pass\n"})
    broken = next(f for f in result.files if f.path == "broken.py")
    assert not broken.parsed and "syntax error" in (broken.error or "")
    assert result.parsed_files == 1 and result.skipped_files == 1


def test_other_languages_need_the_extra_or_a_parser(make_dir):
    result = _bones(make_dir, {"app.js": "function greet(name) { return name; }\n"})
    (file,) = result.files
    if file.parsed:  # the [bones] extra happens to be installed
        assert any(e.name == "greet" and e.kind == "function" for e in file.entries)
    else:
        assert "git-reaper[bones]" in (file.error or "")


def test_treesitter_maps_multiple_languages_when_installed(make_dir):
    pytest.importorskip("tree_sitter_language_pack")
    result = _bones(
        make_dir,
        {
            "app.js": "class Reaper { reap(n) { return n; } }\n",
            "lib.rs": "pub fn reap(n: u32) -> u32 { n }\n",
        },
    )
    files = {f.path: f for f in result.files}
    if not all(f.parsed for f in files.values()):
        pytest.skip("tree-sitter present but this build's Node API is unsupported")
    js = {e.name: e.kind for e in files["app.js"].entries}
    assert js["Reaper"] == "class" and js["reap"] == "method"
    assert any(e.name == "reap" for e in files["lib.rs"].entries)


def test_unrecognized_files_are_not_bones(make_dir):
    result = _bones(make_dir, {"notes.md": "# hi\n", "data.csv": "a,b\n"})
    assert result.files == []


def test_render_marks_skipped_files(make_dir):
    result = _bones(make_dir, {"broken.py": "def nope(:\n"})
    assert "*skipped: syntax error" in render_bones(result)
