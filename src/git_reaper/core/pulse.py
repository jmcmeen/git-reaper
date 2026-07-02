"""Signs-of-life check: the first thing to run when a ritual misbehaves."""

from __future__ import annotations

import importlib.util
import os
import sys

from git_reaper import cache
from git_reaper.gitio import default_backend
from git_reaper.models import PulseCheck, PulseResult

_EXTRAS = {
    "GitPython": ("git", "[git] extra"),
    "tiktoken": ("tiktoken", "[tokens] extra"),
    "textual": ("textual", "[tui] extra"),
}


def pulse() -> PulseResult:
    result = PulseResult()

    git_version = default_backend().version()
    result.checks.append(
        PulseCheck(
            name="git",
            ok=git_version is not None,
            detail=git_version or "git not found on PATH; install git",
        )
    )

    result.checks.append(
        PulseCheck(
            name="python",
            ok=sys.version_info >= (3, 10),
            detail=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )

    for label, (module, hint) in _EXTRAS.items():
        present = importlib.util.find_spec(module) is not None
        result.checks.append(
            PulseCheck(
                name=label,
                ok=True,  # extras are optional; absence is informational
                detail="installed" if present else f"not installed ({hint})",
            )
        )

    catacombs = cache.catacombs_root()
    probe = catacombs
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    writable = os.access(probe, os.W_OK)
    graves = len(cache.list_graves())
    result.checks.append(
        PulseCheck(
            name="catacombs",
            ok=writable,
            detail=f"{catacombs} ({graves} interred)"
            if writable
            else f"{catacombs} is not writable",
        )
    )

    result.checks.append(
        PulseCheck(
            name="tty",
            ok=True,
            detail="color enabled"
            if sys.stderr.isatty() and not os.environ.get("NO_COLOR")
            else "plain output (non-tty or NO_COLOR)",
        )
    )
    return result
