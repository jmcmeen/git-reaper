"""Backend behaviors that aren't tied to one command: the shallow/unshallow
dance that lets history commands work against a previously-shallow cache."""

from __future__ import annotations

from pathlib import Path

from git_reaper.gitio import SubprocessGit


def test_fetch_unshallows_a_shallow_clone(necropolis, tmp_path):
    # A shallow clone (as harvest/conjure leave in the catacombs) sees only the
    # tip; a full-depth fetch must unshallow it so chronicle/souls/etc. see all.
    backend = SubprocessGit()
    dest = tmp_path / "shallow"
    backend.clone(f"file://{necropolis}", dest, depth=1)
    assert backend._is_shallow(dest)
    assert len(backend.log(dest)) == 1  # only the tip is present

    backend.fetch(dest, depth=None)  # the history commands' full-depth fetch
    assert not backend._is_shallow(dest)
    assert len(backend.log(dest)) == 5  # all of main's history is now here


def test_fetch_unshallow_is_a_noop_on_a_full_clone(necropolis, tmp_path):
    # --unshallow on a complete repo errors; the shallow guard must skip it.
    backend = SubprocessGit()
    dest = tmp_path / "full"
    backend.clone(f"file://{necropolis}", dest, depth=None)
    assert not backend._is_shallow(dest)
    backend.fetch(dest, depth=None)  # must not raise
    assert len(backend.log(dest)) == 5


def test_shallow_clone_left_alone_when_depth_kept(necropolis, tmp_path):
    backend = SubprocessGit()
    dest = tmp_path / "still_shallow"
    backend.clone(f"file://{necropolis}", dest, depth=1)
    backend.fetch(dest, depth=1)  # a shallow refresh stays shallow
    assert backend._is_shallow(Path(dest))
