"""Banshee: the watcher that screams.

A polling watcher (portable everywhere the reaper runs -- no inotify, no
FSEvents, no extra deps) that fingerprints the non-ignored tree and screams
(re-runs a recipe) when anything changes. The loop takes an injectable
sleep and a cycle cap so tests never wait on a real clock; the CLI wires
the scream to `cast`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from git_reaper.ignore import IgnoreMatcher, walk_files

DEFAULT_INTERVAL = 2.0

#: A fingerprint: relative path -> (size, mtime_ns).
Snapshot = dict[str, tuple[int, int]]


def snapshot(root: Path, excludes: list[str] | None = None) -> Snapshot:
    """Fingerprint every non-ignored file (size and mtime, cheap to poll)."""
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    taken: Snapshot = {}
    for path in walk_files(root, matcher):
        try:
            stat = path.stat()
        except OSError:
            continue  # deleted mid-walk; the next poll will notice
        taken[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return taken


def changed(before: Snapshot, after: Snapshot) -> list[str]:
    """The paths that appeared, vanished, or changed shape, sorted."""
    moved = [path for path in after if before.get(path) != after[path]]
    moved.extend(path for path in before if path not in after)
    return sorted(set(moved))


def haunt(
    root: Path,
    scream: Callable[[list[str]], None],
    interval: float = DEFAULT_INTERVAL,
    excludes: list[str] | None = None,
    once: bool = False,
    max_polls: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Watch root; call scream(changed_paths) on every change.

    Returns how many times the banshee screamed. `once` stops after the
    first scream; `max_polls` bounds the vigil (tests, mostly). The caller
    handles KeyboardInterrupt -- the banshee herself never stops willingly.
    """
    before = snapshot(root, excludes)
    screams = 0
    polls = 0
    while max_polls is None or polls < max_polls:
        sleep(interval)
        polls += 1
        after = snapshot(root, excludes)
        moved = changed(before, after)
        before = after
        if moved:
            screams += 1
            scream(moved)
            if once:
                break
    return screams
