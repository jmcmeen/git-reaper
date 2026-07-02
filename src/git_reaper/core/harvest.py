"""The flagship: gather files matching patterns and prepare them for
concatenation. Returns a HarvestResult; rendering lives in formatters/."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from git_reaper import fsutil, schemas
from git_reaper.core.provenance import make_provenance
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import FileEntry, HarvestResult, RepoRef

DEFAULT_PATTERNS = ("*.md",)


class CapExceeded(RuntimeError):
    """The total size cap was hit. The message says exactly where."""


def _matches(rel_path: str, patterns: tuple[str, ...]) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_path, pat) for pat in patterns)


def harvest(
    repo: RepoRef,
    patterns: tuple[str, ...] = DEFAULT_PATTERNS,
    excludes: list[str] | None = None,
    max_file_size: int | None = None,
    max_total_size: int | None = None,
    include_binary: bool = False,
    invoked: str = "reaper harvest",
    generated: str | None = None,
) -> HarvestResult:
    """Gather every matching file under the resolved source.

    Skips are never silent: each skipped file is recorded with its reason
    so the report can show exactly what was left in the ground.
    """
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = HarvestResult(
        provenance=make_provenance(schemas.artifact_schema("harvest"), repo, invoked, generated),
        root=str(root),
    )

    for path in walk_files(root, matcher):
        rel = path.relative_to(root).as_posix()
        if not _matches(rel, patterns):
            continue
        size = path.stat().st_size
        if max_file_size is not None and size > max_file_size:
            result.skipped.append(
                FileEntry(
                    path=rel,
                    size_bytes=size,
                    skipped=True,
                    skip_reason=f"over size cap ({fsutil.human_size(size)})",
                )
            )
            continue
        if not include_binary and fsutil.is_binary(path):
            result.skipped.append(
                FileEntry(path=rel, size_bytes=size, skipped=True, skip_reason="binary")
            )
            continue
        if max_total_size is not None and result.total_bytes + size > max_total_size:
            raise CapExceeded(
                f"total size cap {fsutil.human_size(max_total_size)} reached at {rel}; "
                "raise --max-total-size or narrow the pattern"
            )
        entry = FileEntry(path=rel, size_bytes=size, line_count=fsutil.count_lines(path))
        result.files.append(entry)
        result.total_bytes += size
        result.total_lines += entry.line_count

    result.token_estimate = fsutil.estimate_tokens(result.total_bytes)
    result.provenance.files = len(result.files)
    result.provenance.token_estimate = result.token_estimate
    return result
