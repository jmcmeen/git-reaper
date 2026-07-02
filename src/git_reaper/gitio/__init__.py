"""Git backends, abstracted so the engine never shells out directly."""

from git_reaper.gitio.backend import GitBackend, GitError
from git_reaper.gitio.subprocess_git import SubprocessGit

__all__ = ["GitBackend", "GitError", "SubprocessGit", "default_backend"]


def default_backend() -> GitBackend:
    """The zero-dependency default: shell out to git."""
    return SubprocessGit()
