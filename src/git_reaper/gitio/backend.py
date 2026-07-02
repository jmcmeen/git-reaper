"""Abstract git backend.

The subprocess backend is the default; GitPython ships behind the [git]
extra later. Core code depends only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class GitError(RuntimeError):
    """A git operation failed. Message carries the plain cause and path."""


class GitBackend(ABC):
    """The minimal git surface v0.1 needs."""

    @abstractmethod
    def version(self) -> str | None:
        """Installed git version string, or None if git is missing."""

    @abstractmethod
    def is_repo(self, path: Path) -> bool:
        """True if path is inside a git work tree."""

    @abstractmethod
    def clone(self, url: str, dest: Path, depth: int | None = 1, ref: str | None = None) -> None:
        """Clone url into dest (created by the call), shallow by default."""

    @abstractmethod
    def fetch(self, repo: Path, ref: str | None = None, depth: int | None = 1) -> None:
        """Refresh an existing clone."""

    @abstractmethod
    def checkout(self, repo: Path, ref: str) -> None:
        """Check out a branch, tag, or sha."""

    @abstractmethod
    def head_sha(self, repo: Path) -> str | None:
        """Current commit sha, or None outside a repo / before first commit."""

    @abstractmethod
    def current_branch(self, repo: Path) -> str | None:
        """Current branch name, or None when detached or not a repo."""

    @abstractmethod
    def blame(self, repo: Path, rel_path: str) -> list[tuple[str, int]] | None:
        """Per-line (author, author-time epoch), or None when blame fails
        (untracked file, not a repo, no git)."""
