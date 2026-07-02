"""Filesystem helpers: binary detection, size parsing, streaming counts."""

from __future__ import annotations

import re
from pathlib import Path

_CHUNK = 65536
_SNIFF = 8192

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
