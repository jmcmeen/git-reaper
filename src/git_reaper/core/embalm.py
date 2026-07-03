"""Embalm: preserve a repo state in a provenance-stamped tarball.

The snapshot is deterministic (the plan's byte-identical promise): entries
sorted, ownership zeroed, modes normalized, every timestamp pinned to the
HEAD commit's author time (or the epoch for a plain folder) -- the one
wall-clock value in the archive is the provenance stamp itself. A
PROVENANCE file rides at the archive root and a MANIFEST.sha256 makes each
body verifiable, so a snapshot found alone still says exactly what it is
(this also buries the old `hex` idea inside embalm, as planned).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path
from typing import IO, Any

from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import EmbalmResult, RepoRef
from git_reaper.schemas import artifact_schema

_CHUNK = 65536


def _archive_mtime(repo: RepoRef, backend: GitBackend) -> int:
    """HEAD's author time when there is history, the epoch when not."""
    root = Path(repo.path)
    if backend.is_repo(root):
        commits = backend.log(root, ref=repo.ref, max_count=1)
        if commits:
            return commits[0].author_time
    return 0


def embalm(
    repo: RepoRef,
    out: Path,
    excludes: list[str] | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper embalm",
    generated: str | None = None,
) -> EmbalmResult:
    """Write the snapshot tarball and return its ledger."""
    backend = backend or default_backend()
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    files = walk_files(root, matcher)
    mtime = _archive_mtime(repo, backend)
    top = Path(repo.path).name or "corpse"

    result = EmbalmResult(
        provenance=make_provenance(artifact_schema("embalm"), repo, invoked, generated),
        out=str(out),
    )

    manifest_lines: list[str] = []
    out.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()

    with out.open("wb") as raw:
        counting = _Counting(raw, digest)
        # mtime=0 pins the gzip header; the tarball stays byte-identical.
        with (
            gzip.GzipFile(fileobj=counting, mode="wb", mtime=0) as gz,
            tarfile.open(fileobj=gz, mode="w") as tar,
        ):
            for path in files:
                rel = path.relative_to(root).as_posix()
                data = path.read_bytes()
                manifest_lines.append(f"{hashlib.sha256(data).hexdigest()}  {rel}")
                info = _entry(f"{top}/{rel}", len(data), mtime)
                if path.stat().st_mode & 0o100:
                    info.mode = 0o755
                tar.addfile(info, io.BytesIO(data))
                result.files += 1
                result.total_bytes += len(data)
            result.provenance.files = result.files
            provenance = _render_stamp(result)
            manifest = "\n".join(manifest_lines) + "\n" if manifest_lines else ""
            for name, text in (
                (f"{top}/PROVENANCE", provenance),
                (f"{top}/MANIFEST.sha256", manifest),
            ):
                payload = text.encode("utf-8")
                tar.addfile(_entry(name, len(payload), mtime), io.BytesIO(payload))

    result.archive_sha256 = digest.hexdigest()
    result.provenance.files = result.files
    return result


def _entry(name: str, size: int, mtime: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = size
    info.mtime = mtime
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def _render_stamp(result: EmbalmResult) -> str:
    """The provenance block, rendered here to keep formatters out of core."""
    from git_reaper.formatters.markdown import render_provenance

    return render_provenance(result.provenance, "embalm")


class _Counting:
    """A write-through shim that feeds the archive's own sha256."""

    def __init__(self, raw: IO[bytes], digest: Any) -> None:
        self._raw = raw
        self._digest = digest

    def write(self, data: bytes) -> int:
        self._digest.update(data)
        return self._raw.write(data)

    def flush(self) -> None:
        self._raw.flush()
