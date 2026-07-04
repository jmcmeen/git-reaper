"""Filesystem helpers: binary detection, size parsing, streaming counts."""

from __future__ import annotations

import gzip
import io
import os
import re
import shutil
import stat
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

_CHUNK = 65536
_SNIFF = 8192

#: Archive containers a directory-tree output can be packaged into.
ARCHIVE_FORMATS = ("zip", "tar", "tar.gz")
_ARCHIVE_EXT = {"zip": ".zip", "tar": ".tar", "tar.gz": ".tar.gz"}
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)  # zip's date floor; there's no 1970 to pin to

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?I?B?)\s*$", re.IGNORECASE)
_SIZE_UNITS = {
    "": 1,
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}


def parse_size(text: str) -> int:
    """Parse '1MB', '512KiB', '1024' into bytes. Raises ValueError."""
    match = _SIZE_RE.match(text)
    if not match:
        raise ValueError(f"unreadable size: {text!r} (try '1MB', '512KiB', or plain bytes)")
    value, unit = match.groups()
    unit = unit.upper()
    if unit in ("K", "M", "G", "T"):
        unit += "B"
    if unit not in _SIZE_UNITS:
        # The regex is looser than the unit table ('1Ki' slips through).
        raise ValueError(f"unreadable size: {text!r} (try '1MB', '512KiB', or plain bytes)")
    return int(float(value) * _SIZE_UNITS[unit])


def human_size(size: int) -> str:
    """Render bytes for humans: 1.2 MB, 340 B."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1000
    return f"{int(value)} B"


def force_rmtree(path: str | Path) -> None:
    """rmtree that also removes read-only files.

    Git marks object files read-only; on Windows a plain rmtree raises
    PermissionError on them. Clear the bit and retry.
    """

    def _grant_and_retry(func: Any, target: Any, _exc: Any) -> None:
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_grant_and_retry)
    else:
        shutil.rmtree(path, onerror=_grant_and_retry)


def is_binary(path: Path) -> bool:
    """NUL-byte sniff on the first 8 KiB, the same heuristic git uses."""
    try:
        with path.open("rb") as fh:
            return b"\0" in fh.read(_SNIFF)
    except OSError:
        return True


def count_lines(path: Path) -> int:
    """Count newline-terminated lines, streaming; never loads the file."""
    lines = 0
    last = b""
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            lines += chunk.count(b"\n")
            last = chunk
    if last and not last.endswith(b"\n"):
        lines += 1
    return lines


def estimate_tokens(byte_count: int) -> int:
    """Cheap chars/4 heuristic. tiktoken lands behind the [tokens] extra later."""
    return byte_count // 4


def make_archive(source_dir: Path, fmt: str) -> Path:
    """Package source_dir's files into a sibling archive, deterministically.

    Entries are sorted and POSIX-named under a top-level source_dir.name/
    prefix, with ownership/mtime stripped, so two runs over the same tree
    produce byte-identical output (mirrors embalm's tarball discipline).
    source_dir is left untouched; the caller decides whether to remove it.
    """
    if fmt not in ARCHIVE_FORMATS:
        raise ValueError(f"unknown archive format {fmt!r}; use one of {ARCHIVE_FORMATS}")
    dest = source_dir.with_name(source_dir.name + _ARCHIVE_EXT[fmt])
    top = source_dir.name
    paths = sorted(
        (p for p in source_dir.rglob("*") if p.is_file() and not p.is_symlink()),
        key=lambda p: p.relative_to(source_dir).as_posix(),
    )

    if fmt == "zip":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                arcname = f"{top}/{path.relative_to(source_dir).as_posix()}"
                info = zipfile.ZipInfo(arcname, date_time=_ZIP_EPOCH)
                info.external_attr = 0o644 << 16
                zf.writestr(info, path.read_bytes())
        return dest

    with dest.open("wb") as raw:
        if fmt == "tar.gz":
            # mtime=0 pins the gzip header; the tarball stays byte-identical.
            with (
                gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
                tarfile.open(fileobj=gz, mode="w") as tar,
            ):
                _write_tar_entries(tar, paths, source_dir, top)
        else:
            with tarfile.open(fileobj=raw, mode="w") as tar:
                _write_tar_entries(tar, paths, source_dir, top)
    return dest


def _write_tar_entries(tar: tarfile.TarFile, paths: list[Path], source_dir: Path, top: str) -> None:
    for path in paths:
        data = path.read_bytes()
        info = tarfile.TarInfo(f"{top}/{path.relative_to(source_dir).as_posix()}")
        info.size = len(data)
        info.mtime = 0
        info.mode = 0o755 if path.stat().st_mode & 0o100 else 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        tar.addfile(info, io.BytesIO(data))
