"""The catacombs: URL mapping, clone reuse, banish."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from git_reaper import cache
from git_reaper.core.source import resolve_source


def test_grave_path_layouts(isolated_catacombs: Path):
    https = cache.grave_path("https://github.com/jmcmeen/observa.git")
    assert https == isolated_catacombs / "github.com" / "jmcmeen" / "observa"
    ssh = cache.grave_path("git@github.com:jmcmeen/observa.git")
    assert ssh == isolated_catacombs / "github.com" / "jmcmeen" / "observa"


def test_grave_path_file_urls(isolated_catacombs: Path):
    posix = cache.grave_path("file:///tmp/crypt/corpse")
    assert posix == isolated_catacombs / "localhost" / "tmp" / "crypt" / "corpse"
    # Windows as_uri() form: drive letter rides in the path.
    proper = cache.grave_path("file:///C:/repos/corpse")
    assert proper == isolated_catacombs / "localhost" / "C_" / "repos" / "corpse"
    # Hand-typed Windows form: backslashes push the drive into the netloc.
    typed = cache.grave_path("file://C:\\repos\\corpse")
    assert typed == proper


def test_grave_path_rejects_nonsense():
    with pytest.raises(ValueError):
        cache.grave_path("https://github.com/")


def test_remote_clone_lands_in_catacombs_and_is_reused(make_repo, isolated_catacombs: Path):
    # file:// URLs exercise the real clone path without any network.
    origin = make_repo({"README.md": "# origin\n"})
    url = origin.as_uri()

    first = resolve_source(url)
    assert not first.cached
    assert Path(first.repo.path).is_relative_to(isolated_catacombs)
    assert (Path(first.repo.path) / "README.md").read_text() == "# origin\n"
    assert first.repo.sha is not None

    second = resolve_source(url)
    assert second.cached
    assert second.repo.path == first.repo.path


def test_banish_clears_and_respects_age(make_repo, isolated_catacombs: Path):
    origin = make_repo({"README.md": "x\n"})
    resolved = resolve_source(origin.as_uri())

    old = time.time() - 10 * 86400
    os.utime(resolved.repo.path, (old, old))

    kept = cache.banish(older_than_seconds=30 * 86400)
    assert kept.removed == [] and len(kept.kept) == 1

    swept = cache.banish(older_than_seconds=7 * 86400)
    assert len(swept.removed) == 1
    assert not Path(resolved.repo.path).exists()


def test_parse_age():
    assert cache.parse_age("7d") == 7 * 86400
    assert cache.parse_age("12h") == 12 * 3600
    with pytest.raises(ValueError):
        cache.parse_age("fortnight")


def test_local_source_never_touches_cache(make_repo, isolated_catacombs: Path):
    root = make_repo({"README.md": "x\n"})
    resolved = resolve_source(str(root))
    assert resolved.repo.kind == "local"
    assert not isolated_catacombs.exists()


def test_missing_local_path_is_a_plain_error():
    with pytest.raises(FileNotFoundError):
        resolve_source("/no/such/crypt")
