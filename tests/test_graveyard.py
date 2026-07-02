"""The graveyard and its resurrections."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_reaper.core import graveyard
from git_reaper.core.graveyard import ResurrectError
from git_reaper.models import RepoRef


def ref(root: Path) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def test_graveyard_lists_the_dead(necropolis):
    result = graveyard.graveyard(ref(necropolis))
    dead = {d.path for d in result.dead}
    # src/core.py was deleted; docs/old.md died in the rename (renames off).
    assert "src/core.py" in dead
    assert "docs/old.md" in dead
    # Files still in the tree are not in the graveyard.
    assert "README.md" not in dead
    assert "docs/new.md" not in dead


def test_graveyard_records_the_fatal_commit(necropolis):
    result = graveyard.graveyard(ref(necropolis))
    core = next(d for d in result.dead if d.path == "src/core.py")
    assert core.author == "Alice"  # the 'kill core' commit
    assert core.died.startswith("2020-01-10")


def test_resurrect_restores_last_living_bytes(necropolis, tmp_path):
    dst = tmp_path / "risen"
    result = graveyard.resurrect(ref(necropolis), "src/core.py", dst)
    # content as of the parent of the deletion: two lines, not the seed's one.
    assert (dst / "src/core.py").read_text() == "x = 1\ny = 2\n"
    assert result.size_bytes == len("x = 1\ny = 2\n")


def test_resurrect_unknown_file_is_a_clear_error(necropolis, tmp_path):
    with pytest.raises(ResurrectError, match="not in the graveyard"):
        graveyard.resurrect(ref(necropolis), "never/existed.py", tmp_path)


def test_resurrect_refuses_traversal(necropolis, tmp_path):
    with pytest.raises(ResurrectError, match="traversal"):
        graveyard.resurrect(ref(necropolis), "../escape.py", tmp_path)


def test_resurrect_refuses_to_clobber_without_force(necropolis, tmp_path):
    dst = tmp_path / "risen"
    graveyard.resurrect(ref(necropolis), "src/core.py", dst)
    with pytest.raises(ResurrectError, match="already exists"):
        graveyard.resurrect(ref(necropolis), "src/core.py", dst)
    # with force it overwrites cleanly
    result = graveyard.resurrect(ref(necropolis), "src/core.py", dst, force=True)
    assert result.size_bytes > 0
