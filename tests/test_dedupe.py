"""Doppelgangers and bloat."""

from __future__ import annotations

from git_reaper.core.dedupe import bloat, doppelgangers
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import render_bloat, render_doppelgangers


def _repo_ref(make, files):
    return resolve_source(str(make(files))).repo


def test_doppelgangers_cluster_identical_content(make_dir):
    repo = _repo_ref(
        make_dir,
        {
            "a/one.txt": "same soul\n",
            "b/two.txt": "same soul\n",
            "c/three.txt": "same soul\n",
            "unique.txt": "one of a kind\n",
        },
    )
    result = doppelgangers(repo)
    (cluster,) = result.clusters
    assert cluster.paths == ["a/one.txt", "b/two.txt", "c/three.txt"]
    assert cluster.reclaimable_bytes == 2 * cluster.size_bytes
    assert result.reclaimable_bytes == cluster.reclaimable_bytes
    assert result.files_scanned == 4


def test_same_size_different_content_is_no_doppelganger(make_dir):
    repo = _repo_ref(make_dir, {"a.txt": "aaaa\n", "b.txt": "bbbb\n"})
    assert doppelgangers(repo).clusters == []


def test_empty_files_are_convention_not_waste(make_dir):
    repo = _repo_ref(make_dir, {"pkg/__init__.py": "", "lib/__init__.py": ""})
    assert doppelgangers(repo).clusters == []


def test_min_size_floor(make_dir):
    repo = _repo_ref(make_dir, {"a.txt": "tiny\n", "b.txt": "tiny\n"})
    assert doppelgangers(repo, min_size=1000).clusters == []
    assert len(doppelgangers(repo, min_size=1).clusters) == 1


def test_doppelgangers_render(make_dir):
    repo = _repo_ref(make_dir, {"a.txt": "same\n", "b.txt": "same\n"})
    text = render_doppelgangers(doppelgangers(repo))
    assert "- a.txt" in text and "reclaimable" in text


def test_bloat_ranks_the_living(make_dir):
    repo = _repo_ref(make_dir, {"big.bin": "x" * 5000, "small.txt": "x\n"})
    result = bloat(repo, limit=1)
    assert [e.path for e in result.tree] == ["big.bin"]
    assert result.tree_bytes == 5002
    assert result.walls == []  # no history, no walls


def test_bloat_finds_the_body_in_the_walls(make_history):
    root = make_history(
        [
            {"message": "bury a corpse", "write": {"huge.dat": "Z" * 9000, "keep.txt": "k\n"}},
            {"message": "hide the evidence", "delete": ["huge.dat"]},
        ]
    )
    result = bloat(resolve_source(str(root)).repo)
    (wall,) = [e for e in result.walls if e.path == "huge.dat"]
    assert wall.size_bytes == 9000
    assert not wall.in_tree and wall.sha
    assert result.walls_bytes >= 9000
    # the surviving file is not reported as a wall
    assert "keep.txt" not in {e.path for e in result.walls}


def test_bloat_render_shows_both_sections(make_history):
    root = make_history(
        [
            {"message": "seed", "write": {"big.dat": "Z" * 9000, "keep.txt": "k\n"}},
            {"message": "kill", "delete": ["big.dat"]},
        ]
    )
    text = render_bloat(bloat(resolve_source(str(root)).repo))
    assert "## the living" in text and "the walls" in text and "big.dat" in text
