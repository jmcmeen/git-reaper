"""Abstract git backend.

The subprocess backend is the default; GitPython ships behind the [git]
extra later. Core code depends only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class GitError(RuntimeError):
    """A git operation failed. Message carries the plain cause and path."""


# Raw git records live here, at the gitio/core boundary (like blame's tuples),
# not in models.py. models.py is for what formatters render and --schema exports;
# these are internal inputs the history core aggregates over.


@dataclass
class FileChange:
    """One file touched by a commit. insertions/deletions are None for binaries."""

    path: str
    insertions: int | None = None
    deletions: int | None = None


@dataclass
class GitCommit:
    """One commit with its per-file churn. author_date is strict ISO (with tz)."""

    sha: str
    author_name: str
    author_email: str
    author_time: int  # epoch seconds (UTC)
    author_date: str  # strict ISO 8601 with the recorded offset
    subject: str
    body: str = ""
    files: list[FileChange] = field(default_factory=list)


@dataclass
class DeadFileRecord:
    """A file removed by a commit: the path and the fatal commit's metadata."""

    path: str
    sha: str
    date: str
    author: str


@dataclass
class FileEventRecord:
    """One add/modify/delete of a path by a commit (a --name-status row)."""

    path: str
    status: str  # "A", "M", or "D"
    sha: str
    date: str


@dataclass
class BranchRecord:
    """One local branch: its tip, recorded activity, and hygiene flags."""

    name: str
    last_time: int  # epoch seconds of the tip commit
    last_date: str  # strict ISO
    author: str
    merged: bool = False
    gone_upstream: bool = False


@dataclass
class TagRecord:
    """One tag pointing at a commit (annotated tags are dereferenced)."""

    name: str
    sha: str
    date: str


@dataclass
class BlobRecord:
    """One unique blob reachable from history: sha, an example path, size."""

    sha: str
    path: str
    size_bytes: int


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

    # -- history mining (Phase 3) ------------------------------------------

    @abstractmethod
    def log(
        self, repo: Path, ref: str | None = None, max_count: int | None = None
    ) -> list[GitCommit]:
        """Full commit log, newest first, each with per-file numstat churn.
        Rename detection is off for stable parsing; a rename reads as a
        delete plus an add (which is what churn tools want anyway)."""

    @abstractmethod
    def file_log(self, repo: Path, rel_path: str, follow: bool = True) -> list[GitCommit]:
        """Commits that touched one path, newest first, following renames."""

    @abstractmethod
    def rename_history(self, repo: Path, rel_path: str) -> list[str]:
        """Prior names this path has worn, newest first (empty if never renamed)."""

    @abstractmethod
    def deleted_files(self, repo: Path) -> list[DeadFileRecord]:
        """Every file a commit ever removed, newest death first, one row per path."""

    # -- deep mining (Phase 11/12: lineage, revenant) ------------------------

    @abstractmethod
    def pickaxe(
        self, repo: Path, needle: str, regex: bool = False, rel_path: str | None = None
    ) -> list[GitCommit]:
        """Commits whose diffs added or removed the needle (git -S, or -G
        when regex), newest first, with numstat churn."""

    @abstractmethod
    def file_events(self, repo: Path) -> list[FileEventRecord]:
        """Every add/modify/delete event in history, newest first."""

    @abstractmethod
    def show_file(self, repo: Path, rev: str, rel_path: str) -> bytes | None:
        """Raw bytes of a path at a revision, or None if absent there."""

    @abstractmethod
    def branches(self, repo: Path) -> list[BranchRecord]:
        """Local branches with tip activity and merged/gone-upstream flags."""

    # -- object mining (Phase 5: exhume, bloat) -----------------------------

    @abstractmethod
    def blobs(self, repo: Path, ref: str | None = None) -> list[BlobRecord]:
        """Every unique blob reachable from any ref, with one example path
        and its uncompressed size, sorted by sha for determinism.

        `ref` narrows the walk the same way `log`'s does: a single rev walks
        only what it reaches, an `A..B` range walks what `B` reaches minus
        what `A` already did (new blobs since `A`). `None` is every ref."""

    @abstractmethod
    def cat_blob(self, repo: Path, sha: str) -> bytes | None:
        """Raw bytes of one blob, or None if it does not exist."""

    @abstractmethod
    def blob_commit(self, repo: Path, sha: str, path: str) -> tuple[str, str, str] | None:
        """(commit sha, iso date, author) of the oldest commit that touched
        this blob at this path, or None when unattributable."""

    @abstractmethod
    def tags(self, repo: Path) -> list[TagRecord]:
        """Tags with the commit they point at (annotated tags dereferenced)."""
