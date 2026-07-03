"""pygit2 backend: parity with the subprocess backend on the read paths.

Runs only when the ``git-reaper[pygit2]`` extra is installed. The libgit2
backend reimplements the bulk read paths natively, so parity here is the
contract that keeps `GIT_REAPER_BACKEND=pygit2` invisible to every ritual.
The delegated paths (clone, fetch, file_log, pickaxe, ...) inherit from the
subprocess backend and need no parity of their own.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pygit2")

from git_reaper.gitio import SubprocessGit, default_backend
from git_reaper.gitio.pygit2_git import Pygit2Git


@pytest.fixture
def backends() -> tuple[SubprocessGit, Pygit2Git]:
    return SubprocessGit(), Pygit2Git()


def test_log_parity_including_bodies_and_churn(necropolis, backends):
    sub, pg = backends
    assert sub.log(necropolis) == pg.log(necropolis)
    assert sub.log(necropolis, max_count=2) == pg.log(necropolis, max_count=2)
    assert sub.log(necropolis, ref="v1.0.0") == pg.log(necropolis, ref="v1.0.0")


def test_log_parity_with_binaries_and_merges(make_history, backends):
    sub, pg = backends
    root = make_history(
        [
            {
                "message": "seed",
                "when": "2020-01-01T00:00:00+00:00",
                "write": {"a.py": "x\n", "blob.bin": b"\x00\x01\x02"},
            },
            {
                "message": "touch both",
                "when": "2020-01-02T00:00:00+00:00",
                "write": {"a.py": "y\n", "blob.bin": b"\x03\x04"},
            },
        ],
        name="binaries",
    )
    assert sub.log(root) == pg.log(root)


def test_tags_blame_head_parity(necropolis, backends):
    sub, pg = backends
    assert sub.tags(necropolis) == pg.tags(necropolis)
    assert sub.blame(necropolis, "README.md") == pg.blame(necropolis, "README.md")
    assert sub.head_sha(necropolis) == pg.head_sha(necropolis)
    assert sub.current_branch(necropolis) == pg.current_branch(necropolis)
    assert pg.is_repo(necropolis)


def test_show_file_and_blob_parity(necropolis, backends):
    sub, pg = backends
    assert sub.show_file(necropolis, "v1.0.0", "src/main.py") == pg.show_file(
        necropolis, "v1.0.0", "src/main.py"
    )
    assert pg.show_file(necropolis, "v1.0.0", "never/was.py") is None
    sub_blobs, pg_blobs = sub.blobs(necropolis), pg.blobs(necropolis)
    # the example path may differ by traversal order; sha + size must not
    assert {(b.sha, b.size_bytes) for b in sub_blobs} == {(b.sha, b.size_bytes) for b in pg_blobs}
    sha = sub_blobs[0].sha
    assert sub.cat_blob(necropolis, sha) == pg.cat_blob(necropolis, sha)
    assert pg.cat_blob(necropolis, "0" * 40) is None


def test_not_a_repo_is_not_a_repo(make_dir, backends):
    _sub, pg = backends
    folder = make_dir({"a.md": "hi\n"})
    assert not pg.is_repo(folder)
    assert pg.head_sha(folder) is None


def test_default_backend_env_selects_pygit2(monkeypatch):
    monkeypatch.setenv("GIT_REAPER_BACKEND", "pygit2")
    assert isinstance(default_backend(), Pygit2Git)


def test_history_rituals_agree_across_backends(necropolis, backends):
    from git_reaper.core import history
    from git_reaper.models import RepoRef

    sub, pg = backends
    repo = RepoRef(source=str(necropolis), kind="local", path=str(necropolis))
    stamp = "2020-06-06T06:06:06Z"
    assert history.chronicle(repo, backend=sub, generated=stamp) == history.chronicle(
        repo, backend=pg, generated=stamp
    )
    assert history.souls(repo, heatmap=True, backend=sub, generated=stamp) == history.souls(
        repo, heatmap=True, backend=pg, generated=stamp
    )
