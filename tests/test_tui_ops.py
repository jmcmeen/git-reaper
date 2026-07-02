"""The TUI operation registry: the thin adapter's correctness, no Textual.

Runs in the base suite. These lock that each ritual is wired to its own core
function and formatter (the copy-paste risk across a dozen near-identical
entries), that options actually reach the core, and that history rituals are
flagged as needing a repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from git_reaper import tui_ops
from git_reaper.gitio import GitError
from git_reaper.models import RepoRef

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


def ref(root: Path) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def _run(op: tui_ops.Operation, root: Path, **overrides: object) -> tui_ops.ReapResult:
    opts = op.defaults()
    opts.update(overrides)
    return op.run(ref(root), opts)


def test_registry_keys_are_unique_and_indexed():
    keys = [op.key for op in tui_ops.OPERATIONS]
    assert len(keys) == len(set(keys))
    assert set(tui_ops.OPERATIONS_BY_KEY) == set(keys)


def test_every_operation_belongs_to_a_known_group():
    for op in tui_ops.OPERATIONS:
        assert op.group in tui_ops.GROUPS, op.key


def test_each_operation_renders_its_own_artifact(necropolis):
    # A repo satisfies both git and non-git operations. Every ritual must
    # produce an artifact that names its own schema (the anti-copy-paste lock).
    for op in tui_ops.OPERATIONS:
        result = _run(op, necropolis)
        assert result.text.strip(), op.key
        if op.key == "tombstone":
            assert "R I P" in result.text  # art card, not a schema table
        elif op.key == "limbs":
            assert result.text.startswith("```") and "directories," in result.text
        elif op.key == "harvest":
            assert "git-reaper harvest" in result.text  # harvest has no schema line
        else:
            assert f"schema:    {op.key}/v1" in result.text, op.key


def test_reap_result_carries_a_summary(necropolis):
    for op in tui_ops.OPERATIONS:
        assert _run(op, necropolis).summary, op.key


def test_history_operations_are_flagged():
    needs = {op.key for op in tui_ops.OPERATIONS if op.needs_git}
    assert needs == {
        "chronicle", "souls", "haunt", "graveyard", "rot", "ghosts",
        "tombstone", "exhume", "omens",
    }


def test_non_git_operations_work_on_a_plain_folder(make_dir):
    folder = make_dir({"README.md": "# hi\n", "a.py": "x = 1\n"})
    for op in tui_ops.OPERATIONS:
        if op.needs_git:
            continue
        assert _run(op, folder).text.strip(), op.key


def test_history_operation_on_a_plain_folder_errors(make_dir):
    folder = make_dir({"a.txt": "hi\n"})
    chronicle = tui_ops.OPERATIONS_BY_KEY["chronicle"]
    with pytest.raises(GitError):
        _run(chronicle, folder)


# -- options actually reach the core -----------------------------------------


def test_format_option_dispatches_to_each_formatter(necropolis):
    census = tui_ops.OPERATIONS_BY_KEY["census"]
    assert _run(census, necropolis, format="md").text.startswith("<!--")
    assert _run(census, necropolis, format="json").text.lstrip().startswith("{")
    assert "extension,language" in _run(census, necropolis, format="csv").text
    assert _run(census, necropolis, format="html").text.startswith("<!DOCTYPE html>")


def test_lens_option_changes_omens(necropolis):
    omens = tui_ops.OPERATIONS_BY_KEY["omens"]
    all_lens = _run(omens, necropolis, lens="all", format="json").text
    size_lens = _run(omens, necropolis, lens="size", format="json").text
    assert '"lens": "all"' in all_lens
    assert '"lens": "size"' in size_lens


def test_heatmap_toggle_changes_souls(necropolis):
    souls = tui_ops.OPERATIONS_BY_KEY["souls"]
    with_heatmap = _run(souls, necropolis, heatmap=True).text
    without = _run(souls, necropolis, heatmap=False).text
    assert "activity" in with_heatmap and "activity" not in without


def test_cursed_flag_on_a_leaky_repo(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})
    result = _run(tui_ops.OPERATIONS_BY_KEY["exhume"], root)
    assert result.cursed
    assert AWS_KEY not in result.text  # masked, always
    clean = make_repo({"ok.md": "nothing\n"}, name="clean")
    assert not _run(tui_ops.OPERATIONS_BY_KEY["exhume"], clean).cursed


def test_defaults_cover_every_option():
    for op in tui_ops.OPERATIONS:
        defaults = op.defaults()
        assert set(defaults) == {opt.name for opt in op.options}, op.key
