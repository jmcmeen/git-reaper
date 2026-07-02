"""GitPython backend: parity with the subprocess backend.

Runs only when the ``git-reaper[git]`` extra is installed. Both backends drive
the same git and share the parsers, so every method must return byte-identical
structures on the same repo -- that equality is the whole contract.
"""

from __future__ import annotations

import pytest

pytest.importorskip("git")

from git_reaper.core import history
from git_reaper.gitio import SubprocessGit
from git_reaper.gitio.gitpython_git import GitPythonGit
from git_reaper.models import RepoRef


@pytest.fixture
def backends() -> tuple[SubprocessGit, GitPythonGit]:
    return SubprocessGit(), GitPythonGit()


def test_log_parity(necropolis, backends):
    sub, gp = backends
    assert sub.log(necropolis) == gp.log(necropolis)


def test_file_log_and_renames_parity(necropolis, backends):
    sub, gp = backends
    assert sub.file_log(necropolis, "docs/new.md") == gp.file_log(necropolis, "docs/new.md")
    assert sub.rename_history(necropolis, "docs/new.md") == gp.rename_history(
        necropolis, "docs/new.md"
    )


def test_deleted_branches_tags_parity(necropolis, backends):
    sub, gp = backends
    assert sub.deleted_files(necropolis) == gp.deleted_files(necropolis)
    assert sub.branches(necropolis) == gp.branches(necropolis)
    assert sub.tags(necropolis) == gp.tags(necropolis)


def test_show_file_parity_returns_exact_bytes(necropolis, backends):
    sub, gp = backends
    dead = sub.deleted_files(necropolis)
    core = next(d for d in dead if d.path == "src/core.py")
    sub_bytes = sub.show_file(necropolis, f"{core.sha}~1", "src/core.py")
    gp_bytes = gp.show_file(necropolis, f"{core.sha}~1", "src/core.py")
    assert sub_bytes == gp_bytes == b"x = 1\ny = 2\n"


def test_blame_and_head_parity(necropolis, backends):
    sub, gp = backends
    assert sub.blame(necropolis, "README.md") == gp.blame(necropolis, "README.md")
    assert sub.head_sha(necropolis) == gp.head_sha(necropolis)
    assert sub.current_branch(necropolis) == gp.current_branch(necropolis)


def test_blob_mining_parity(necropolis, backends):
    sub, gp = backends
    sub_blobs = sub.blobs(necropolis)
    assert sub_blobs == gp.blobs(necropolis)
    # cat_blob returns identical bytes, and attribution agrees.
    blob = next(b for b in sub_blobs if b.path == "src/core.py")
    assert sub.cat_blob(necropolis, blob.sha) == gp.cat_blob(necropolis, blob.sha)
    assert sub.blob_commit(necropolis, blob.sha, blob.path) == gp.blob_commit(
        necropolis, blob.sha, blob.path
    )


def test_full_command_parity_via_core(necropolis, backends):
    # The public commands must agree end-to-end, not just the raw backend.
    sub, gp = backends
    ref = RepoRef(source=str(necropolis), kind="local", path=str(necropolis))
    a = history.chronicle(ref, backend=sub, generated="2020-01-01T00:00:00Z")
    b = history.chronicle(ref, backend=gp, generated="2020-01-01T00:00:00Z")
    assert a == b


def test_cli_honors_backend_env(necropolis, monkeypatch):
    from typer.testing import CliRunner

    from git_reaper.cli import app

    monkeypatch.setenv("GIT_REAPER_BACKEND", "gitpython")
    result = CliRunner().invoke(app, ["--plain", "chronicle", str(necropolis), "--format", "json"])
    assert result.exit_code == 0
    assert '"schema": "chronicle/v1"' in result.stdout


def test_missing_extra_raises_clear_error(monkeypatch):
    # Simulate the extra being absent: the selector must fail loudly, not vanish.
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "git":
            raise ImportError("no git module")
        return real_import(name, *args, **kwargs)

    from git_reaper.gitio.backend import GitError
    from git_reaper.gitio.gitpython_git import GitPythonGit

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(GitError, match="git-reaper\\[git\\]"):
        GitPythonGit()
