"""Git backends, abstracted so the engine never shells out directly."""

from git_reaper.gitio.backend import (
    BlobRecord,
    BranchRecord,
    DeadFileRecord,
    FileChange,
    FileEventRecord,
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
    "FileEventRecord",
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
    (needs the `git-reaper[git]` extra), or GIT_REAPER_BACKEND=pygit2 for the
    libgit2 read-path backend (`git-reaper[pygit2]`, the performance pass); a
    clear error fires if the chosen extra is absent.
    """
    import os

    choice = os.environ.get("GIT_REAPER_BACKEND", "").strip().lower()
    if choice in ("gitpython", "git"):
        from git_reaper.gitio.gitpython_git import GitPythonGit

        return GitPythonGit()
    if choice == "pygit2":
        from git_reaper.gitio.pygit2_git import Pygit2Git

        return Pygit2Git()
    return SubprocessGit()
