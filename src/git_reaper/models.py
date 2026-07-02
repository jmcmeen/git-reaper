"""Result models. Every core function returns these, never formatted strings.

Formatting is a separate layer (formatters/); the CLI and TUI only present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SourceKind = Literal["local", "remote"]


@dataclass
class RepoRef:
    """Where the data came from: a local path or a remote clone."""

    source: str
    kind: SourceKind
    path: str
    ref: str | None = None
    sha: str | None = None


@dataclass
class Provenance:
    """Stamp carried by every combined or packed artifact."""

    schema: str
    source: str
    ref: str | None
    sha: str | None
    generated: str
    tool_version: str
    invoked: str
    files: int = 0
    token_estimate: int = 0


@dataclass
class FileEntry:
    """One file the reaper looked at. Paths are POSIX-style and relative."""

    path: str
    size_bytes: int = 0
    line_count: int = 0
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class HarvestResult:
    """The flagship: gathered files ready to be concatenated."""

    provenance: Provenance
    root: str
    files: list[FileEntry] = field(default_factory=list)
    skipped: list[FileEntry] = field(default_factory=list)
    total_bytes: int = 0
    total_lines: int = 0
    token_estimate: int = 0


@dataclass
class TreeNode:
    """One node in a hierarchical listing."""

    name: str
    path: str
    is_dir: bool
    size_bytes: int = 0
    line_count: int = 0
    children: list[TreeNode] = field(default_factory=list)


@dataclass
class TreeResult:
    """A hierarchical file listing. Works on any folder, git or not."""

    provenance: Provenance
    root: TreeNode
    dir_count: int = 0
    file_count: int = 0
    total_bytes: int = 0


@dataclass
class PulseCheck:
    """One signs-of-life check."""

    name: str
    ok: bool
    detail: str


@dataclass
class PulseResult:
    """Doctor report: is this corpse fit for necromancy?"""

    checks: list[PulseCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


@dataclass
class CacheEntry:
    """One interred repo in the catacombs."""

    path: str
    url: str
    size_bytes: int
    last_used: float


@dataclass
class BanishResult:
    """What the exorcism removed."""

    removed: list[CacheEntry] = field(default_factory=list)
    kept: list[CacheEntry] = field(default_factory=list)
    reclaimed_bytes: int = 0
