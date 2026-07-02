"""Git backends, abstracted so the engine never shells out directly."""

from git_reaper.gitio.backend import (
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
    """The zero-dependency default: shell out to git."""
    return SubprocessGit()
