"""Branch and file hygiene: ghosts and rot."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from git_reaper.core import hygiene
from git_reaper.models import RepoRef

NOW = datetime(2020, 3, 1, tzinfo=timezone.utc).timestamp()


def ref(root: Path) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def test_ghosts_lists_branches_with_merged_flag(necropolis):
    result = hygiene.ghosts(ref(necropolis), now=NOW)
    by_name = {b.name: b for b in result.branches}
    assert set(by_name) == {"main", "feature"}
    # feature was branched off main but never merged back.
    assert by_name["feature"].merged is False
    assert by_name["main"].merged is True


def test_ghosts_flags_stale_past_threshold(necropolis):
    # main's tip is 2020-01-10; feature's is 2020-02-01. With "now" at March 1
    # and a 40-day threshold, main (>50d idle) is stale, feature (~29d) is not.
    result = hygiene.ghosts(ref(necropolis), than_days=40, now=NOW)
    by_name = {b.name: b for b in result.branches}
    assert result.threshold_days == 40
    assert by_name["main"].stale is True
    assert by_name["feature"].stale is False


def test_rot_ranks_the_most_neglected_first(necropolis):
    result = hygiene.rot(ref(necropolis), now=NOW)
    paths = [f.path for f in result.files]
    # only surviving files, README.md (Jan 6) the stalest of them.
    assert paths[0] == "README.md"
    assert "src/core.py" not in paths  # deleted; cannot rot
    assert set(paths) == {"README.md", "docs/new.md", "src/main.py"}


def test_rot_ages_are_computed_from_now(necropolis):
    result = hygiene.rot(ref(necropolis), now=NOW)
    readme = next(f for f in result.files if f.path == "README.md")
    # 2020-01-06T02:00 -> 2020-03-01T00:00 is 54 whole days (floored).
    assert readme.age_days == 54


def test_rot_limit(necropolis):
    result = hygiene.rot(ref(necropolis), limit=1, now=NOW)
    assert len(result.files) == 1
    assert result.files[0].path == "README.md"
