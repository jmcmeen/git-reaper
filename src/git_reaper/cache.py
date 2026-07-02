"""The catacombs: the clone cache.

Remote clones land in a content-addressed cache under
``~/.cache/git-reaper/catacombs/<host>/<owner>/<repo>``, shallow by default,
reused across runs, and cleared by ``banish``. Local ``file://`` sources are
buried flat as ``localhost/<name>-<digest>`` to stay inside Windows path
limits.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from git_reaper import fsutil
from git_reaper.models import BanishResult, CacheEntry

_SCP_RE = re.compile(r"^(?:\w+@)?(?P<host>[\w.-]+):(?P<path>.+)$")


def catacombs_root() -> Path:
    """Cache root, overridable via GIT_REAPER_CACHE for tests and CI."""
    override = os.environ.get("GIT_REAPER_CACHE")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(xdg) / "git-reaper" / "catacombs"


def _sanitize(part: str) -> str:
    part = part.strip("/").removesuffix(".git")
    return re.sub(r"[^\w.-]", "_", part) or "_"


def grave_path(url: str) -> Path:
    """Map a remote URL to its plot in the catacombs."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        # Tolerate Windows spellings (file://C:\repos\x): backslashes never
        # delimit for urlparse, so the drive letter lands in netloc.
        path = parsed.path.replace("\\", "/")
        if re.match(r"^[A-Za-z]:", parsed.netloc):
            path = parsed.netloc.replace("\\", "/") + path
        path = path.strip("/")
        if not path:
            raise ValueError(f"URL has no repository path: {url!r}")
        # Local paths can be arbitrarily deep; mirroring them under the
        # catacombs would breach Windows' 260-char path limit. Bury them
        # flat: basename plus a short digest of the full path.
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]
        name = _sanitize(path.rsplit("/", 1)[-1])
        return catacombs_root() / "localhost" / f"{name}-{digest}"
    if parsed.scheme:
        host, path = parsed.netloc or "localhost", parsed.path
    else:
        scp = _SCP_RE.match(url)
        if not scp:
            raise ValueError(f"cannot read this incantation as a repo URL: {url!r}")
        host, path = scp.group("host"), scp.group("path")
    segments = [_sanitize(seg) for seg in path.strip("/").split("/") if seg]
    if not segments:
        raise ValueError(f"URL has no repository path: {url!r}")
    return catacombs_root() / _sanitize(host) / Path(*segments)


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def list_graves() -> list[CacheEntry]:
    """Every interred repo, oldest first."""
    root = catacombs_root()
    entries: list[CacheEntry] = []
    if not root.is_dir():
        return entries
    for git_dir in sorted(root.rglob(".git")):
        repo = git_dir.parent
        marker = repo / ".git-reaper-url"
        url = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
        entries.append(
            CacheEntry(
                path=str(repo),
                url=url,
                size_bytes=_dir_size(repo),
                last_used=repo.stat().st_mtime,
            )
        )
    entries.sort(key=lambda e: e.last_used)
    return entries


def mark_grave(repo_path: Path, url: str) -> None:
    """Record the source URL and refresh the last-used stamp."""
    (repo_path / ".git-reaper-url").write_text(url + "\n", encoding="utf-8")
    os.utime(repo_path)


def banish(older_than_seconds: float | None = None) -> BanishResult:
    """Clear the catacombs. With older_than, a partial exorcism."""
    result = BanishResult()
    cutoff = time.time() - older_than_seconds if older_than_seconds is not None else None
    for entry in list_graves():
        if cutoff is not None and entry.last_used > cutoff:
            result.kept.append(entry)
            continue
        try:
            fsutil.force_rmtree(entry.path)
        except OSError:
            # A grave we cannot dig up (locked file?) is kept, not "removed".
            result.kept.append(entry)
            continue
        result.removed.append(entry)
        result.reclaimed_bytes += entry.size_bytes
    return result


_AGE_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.IGNORECASE)
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_age(text: str) -> float:
    """Parse '7d', '12h', '90m' into seconds. Raises ValueError."""
    match = _AGE_RE.match(text)
    if not match:
        raise ValueError(f"unreadable age: {text!r} (try '7d', '12h', '30m')")
    value, unit = match.groups()
    return int(value) * _AGE_UNITS[unit.lower()]
