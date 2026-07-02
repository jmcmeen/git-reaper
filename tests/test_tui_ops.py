"""The TUI operation registry: the thin adapter's correctness, no Textual.

Runs in the base suite. These lock that each ritual is wired to its own core
function and formatter (the copy-paste risk across a dozen near-identical
entries), and that history rituals are flagged as needing a repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from git_reaper import tui_ops
from git_reaper.gitio import GitError
from git_reaper.models import RepoRef


def ref(root: Path) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def test_registry_keys_are_unique_and_indexed():
    keys = [op.key for op in tui_ops.OPERATIONS]
    assert len(keys) == len(set(keys))
    assert set(tui_ops.OPERATIONS_BY_KEY) == set(keys)


def test_each_operation_renders_its_own_artifact(necropolis):
    # A repo satisfies both git and non-git operations. Every ritual must
    # produce a provenance-stamped artifact naming its own schema.
    for op in tui_ops.OPERATIONS:
        text = op.run(ref(necropolis))
        assert text.strip(), op.key
        if op.key == "tombstone":
            assert "R I P" in text  # art card, not a schema table
        elif op.key == "limbs":
            assert text.startswith("```") and "directories," in text  # fenced listing
        else:
            assert f"schema:    {op.key}/v1" in text, op.key


def test_history_operations_are_flagged(necropolis):
    needs = {op.key for op in tui_ops.OPERATIONS if op.needs_git}
    assert needs == {"chronicle", "souls", "haunt", "graveyard", "rot", "ghosts", "tombstone"}


def test_non_git_operations_work_on_a_plain_folder(make_dir):
    folder = make_dir({"README.md": "# hi\n", "a.py": "x = 1\n"})
    for op in tui_ops.OPERATIONS:
        if op.needs_git:
            continue
        assert op.run(ref(folder)).strip(), op.key


def test_history_operation_on_a_plain_folder_errors(make_dir):
    folder = make_dir({"a.txt": "hi\n"})
    chronicle = tui_ops.OPERATIONS_BY_KEY["chronicle"]
    with pytest.raises(GitError):
        chronicle.run(ref(folder))
