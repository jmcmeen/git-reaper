"""Hierarchical file listing. Works on any folder, git or not."""

from __future__ import annotations

from pathlib import Path

from git_reaper import fsutil, schemas
from git_reaper.core.provenance import make_provenance
from git_reaper.ignore import IgnoreMatcher
from git_reaper.models import RepoRef, TreeNode, TreeResult


def tree(
    repo: RepoRef,
    max_depth: int | None = None,
    dirs_only: bool = False,
    with_sizes: bool = False,
    with_lines: bool = False,
    excludes: list[str] | None = None,
    invoked: str = "reaper limbs",
    generated: str | None = None,
) -> TreeResult:
    """Build the hierarchy, honoring ignore rules and the depth limit."""
    root_path = Path(repo.path)
    matcher = IgnoreMatcher(root_path, extra_excludes=excludes)
    result = TreeResult(
        provenance=make_provenance(schemas.artifact_schema("limbs"), repo, invoked, generated),
        root=TreeNode(name=root_path.name or str(root_path), path=".", is_dir=True),
    )

    def _build(directory: Path, node: TreeNode, depth: int) -> None:
        if max_depth is not None and depth >= max_depth:
            return
        for entry in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
            rel = entry.relative_to(root_path).as_posix()
            if entry.is_symlink() or matcher.ignored(rel, is_dir=entry.is_dir()):
                continue
            if entry.is_dir():
                child = TreeNode(name=entry.name, path=rel, is_dir=True)
                node.children.append(child)
                result.dir_count += 1
                _build(entry, child, depth + 1)
                child.size_bytes = sum(c.size_bytes for c in child.children)
            elif entry.is_file() and not dirs_only:
                size = entry.stat().st_size if with_sizes or with_lines else 0
                lines = 0
                if with_lines and not fsutil.is_binary(entry):
                    lines = fsutil.count_lines(entry)
                child = TreeNode(
                    name=entry.name, path=rel, is_dir=False, size_bytes=size, line_count=lines
                )
                node.children.append(child)
                result.file_count += 1
                result.total_bytes += size

    _build(root_path, result.root, 0)
    result.root.size_bytes = result.total_bytes
    return result
