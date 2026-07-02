"""History mining: chronicle, souls, haunt, autopsy, tombstone.

Every commit in the `necropolis` fixture has a pinned date, so these assertions
are stable across machines and clocks. Age math takes an injected `now`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from git_reaper.core import history
from git_reaper.models import RepoRef

# A fixed "today" well after the last commit, for deterministic age math.
NOW = datetime(2020, 3, 1, tzinfo=timezone.utc).timestamp()


def ref(root: Path) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def test_chronicle_parses_all_commits_including_multiline_body(necropolis):
    result = history.chronicle(ref(necropolis))
    # five commits on main (the sixth lives on the unmerged feature branch).
    assert len(result.commits) == 5
    subjects = [c.message for c in result.commits]
    # The multiline body must not leak into the subject or split the record.
    assert "rename doc" in subjects
    assert all("\n" not in s for s in subjects)


def test_chronicle_churn_is_counted(necropolis):
    result = history.chronicle(ref(necropolis))
    seed = next(c for c in result.commits if c.message == "seed")
    assert seed.files_changed == 2
    assert seed.insertions == 2 and seed.deletions == 0


def test_chronicle_changelog_groups_under_the_tag(necropolis):
    result = history.chronicle(ref(necropolis), changelog=True)
    assert [s.tag for s in result.changelog] == ["v1.0.0"]
    assert len(result.changelog[0].commits) == 5


def test_souls_ledger_and_bus_factor(necropolis):
    result = history.souls(ref(necropolis))
    by_name = {s.name: s for s in result.souls}
    assert set(by_name) == {"Alice", "Bob"}  # Carol is on the unmerged branch
    assert by_name["Alice"].commits == 3
    assert by_name["Bob"].commits == 2
    assert result.total_commits == 5
    assert result.bus_factor == 1  # Alice alone crosses half the commits


def test_souls_first_and_last_seen(necropolis):
    result = history.souls(ref(necropolis))
    alice = next(s for s in result.souls if s.name == "Alice")
    assert alice.first_seen.startswith("2020-01-06")
    assert alice.last_seen.startswith("2020-01-10")


def test_souls_heatmap_and_witching_hour(necropolis):
    result = history.souls(ref(necropolis), heatmap=True)
    assert result.heatmap is not None
    assert len(result.heatmap) == 7 and len(result.heatmap[0]) == 24
    # Two commits landed Monday 02:00 (recorded tz), the clear peak.
    assert result.heatmap[0][2] == 2
    assert result.witching_hour == "Mon 02:00"


def test_souls_heatmap_uses_recorded_timezone(necropolis):
    # Recorded offset is +00:00, so the hour is 02 regardless of the host tz.
    result = history.souls(ref(necropolis), heatmap=True)
    assert sum(sum(row) for row in result.heatmap) == 5


def test_haunt_ranks_core_highest(necropolis):
    result = history.haunt(ref(necropolis))
    top = result.hotspots[0]
    assert top.path == "src/core.py"  # touched by three commits
    assert top.commits == 3
    assert top.churn == top.insertions + top.deletions


def test_autopsy_follows_the_rename(necropolis):
    result = history.autopsy(ref(necropolis), "docs/new.md", now=NOW)
    assert "docs/old.md" in result.former_names
    assert result.created.startswith("2020-01-08")  # the original 'add doc'
    assert result.commits == 2
    assert result.exists is True


def test_autopsy_blame_age_summary(necropolis):
    result = history.autopsy(ref(necropolis), "README.md", now=NOW)
    assert result.blame_lines == 1
    assert result.median_age_days is not None and result.median_age_days > 0


def test_tombstone_vitals(necropolis):
    result = history.tombstone(ref(necropolis), now=NOW)
    assert result.born.startswith("2020-01-06")
    assert result.last.startswith("2020-01-10")
    assert result.commits == 5
    assert result.souls == 2
    assert result.last_words == "kill core"
    assert result.witching_hour == "Mon 02:00"
    assert result.age_days > 0


def test_chronicle_handles_binary_files(make_history):
    # git renders binary churn as "-\t-\tpath"; the parser must not choke and
    # must report zero (not None) churn for it. Kept off the shared fixture so
    # its exact-count assertions stay intact.
    root = make_history(
        [
            {
                "message": "add an image",
                "when": "2020-01-06T02:00:00+00:00",
                "write": {"logo.png": b"\x89PNG\r\n\x1a\n\x00\x01\x02\x03"},
            }
        ]
    )
    result = history.chronicle(ref(root))
    assert len(result.commits) == 1
    commit = result.commits[0]
    assert commit.files_changed == 1
    assert commit.insertions == 0 and commit.deletions == 0
    # and haunt aggregates the binary without error
    hot = history.haunt(ref(root)).hotspots
    assert hot[0].path == "logo.png"
    assert hot[0].churn == 0


def test_history_on_a_plain_folder_is_a_clear_error(make_dir):
    import pytest

    from git_reaper.gitio import GitError

    folder = make_dir({"a.txt": "hi\n"})
    with pytest.raises(GitError, match="not a git repository"):
        history.chronicle(ref(folder))
