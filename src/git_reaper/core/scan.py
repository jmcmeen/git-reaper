"""Unfinished business: TODO / FIXME / HACK / XXX markers.

Authors come from git blame when the source is a repo; --age adds how long
each marker has haunted the codebase (relative to the provenance timestamp,
so reports stay deterministic for a fixed `generated`).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from git_reaper import fsutil
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import Marker, RepoRef, UnfinishedResult
from git_reaper.schemas import artifact_schema

MARKERS = ("TODO", "FIXME", "HACK", "XXX")

_MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b:?\s*(.*)")
_MAX_TEXT = 200


def unfinished(
    repo: RepoRef,
    excludes: list[str] | None = None,
    with_age: bool = False,
    invoked: str = "reaper unfinished",
    generated: str | None = None,
    backend: GitBackend | None = None,
) -> UnfinishedResult:
    """Scan text files for markers; blame fills in authors when possible."""
    backend = backend or default_backend()
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = UnfinishedResult(
        provenance=make_provenance(artifact_schema("unfinished"), repo, invoked, generated)
    )
    in_repo = backend.is_repo(root)
    now = datetime.strptime(result.provenance.generated, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )

    for path in walk_files(root, matcher):
        if fsutil.is_binary(path):
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        found: list[Marker] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = _MARKER_RE.search(line)
            if match:
                found.append(
                    Marker(
                        path=rel,
                        line=lineno,
                        marker=match.group(1),
                        text=match.group(2).strip()[:_MAX_TEXT],
                    )
                )
        if not found:
            continue
        blame = backend.blame(root, rel) if in_repo else None
        if blame:
            for marker in found:
                if marker.line <= len(blame):
                    author, when = blame[marker.line - 1]
                    marker.author = author
                    if with_age:
                        age = now - datetime.fromtimestamp(when, tz=timezone.utc)
                        marker.age_days = max(0, age.days)
        result.markers.extend(found)

    result.counts = {name: 0 for name in MARKERS}
    for marker in result.markers:
        result.counts[marker.marker] += 1
    result.counts = {name: count for name, count in result.counts.items() if count}
    result.provenance.files = len({m.path for m in result.markers})
    return result
