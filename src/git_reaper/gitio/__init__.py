"""Git backends, abstracted so the engine never shells out directly."""

from git_reaper.gitio.backend import (
    BlobRecord,
    BranchRecord,
    DeadFileRecord,
    FileChange,
    GitBackend,
    GitCommit,
    GitError,
    TagRecord,
)
from git_reaper.gitio.subprocess_git import SubprocessGit

__all__ = [
    "BlobRecord",
    "BranchRecord",
    "DeadFileRecord",
    "FileChange",
    "GitBackend",
    "GitCommit",
    "GitError",
    "SubprocessGit",
    "TagRecord",
    "default_backend",
]


def default_backend() -> GitBackend:
    """The zero-dependency subprocess backend by default.

    Set GIT_REAPER_BACKEND=gitpython to use the optional GitPython backend
    (needs the `git-reaper[git]` extra); a clear error fires if it is absent.
    """
    import os

    choice = os.environ.get("GIT_REAPER_BACKEND", "").strip().lower()
    if choice in ("gitpython", "git"):
        from git_reaper.gitio.gitpython_git import GitPythonGit

        return GitPythonGit()
    return SubprocessGit()
