"""Ignore-rule matching: .gitignore, .reaperignore, and CLI excludes.

Never silently vacuum up node_modules or .venv: the matcher honors the
repo's own .gitignore, a project-level .reaperignore, and ad-hoc globs,
all with gitignore semantics via pathspec.
"""

from __future__ import annotations

from pathlib import Path

import pathspec

#: Directories nobody ever wants reaped, even outside a git repo.
ALWAYS_IGNORED = (".git",)

REAPERIGNORE = ".reaperignore"
GITIGNORE = ".gitignore"


class IgnoreMatcher:
    """Decides which paths the reaper must not touch."""

    def __init__(self, root: Path, extra_excludes: list[str] | None = None) -> None:
        self.root = root
        lines: list[str] = []
        for name in (GITIGNORE, REAPERIGNORE):
            candidate = root / name
            if candidate.is_file():
                lines.extend(candidate.read_text(encoding="utf-8", errors="replace").splitlines())
        lines.extend(extra_excludes or [])
        self._spec = pathspec.GitIgnoreSpec.from_lines(lines)

    def ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Check a POSIX-style relative path against all rules."""
        parts = rel_path.split("/")
        if parts[0] in ALWAYS_IGNORED:
            return True
        if is_dir:
            rel_path += "/"
        return self._spec.match_file(rel_path)


def walk_files(root: Path, matcher: IgnoreMatcher) -> list[Path]:
    """All non-ignored files under root, sorted for deterministic output."""
    found: list[Path] = []

    def _walk(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            rel = entry.relative_to(root).as_posix()
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if not matcher.ignored(rel, is_dir=True):
                    _walk(entry)
            elif entry.is_file() and not matcher.ignored(rel):
                found.append(entry)

    _walk(root)
    return found
