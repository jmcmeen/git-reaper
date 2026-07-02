"""Provenance stamps: every combined artifact says where it came from."""

from __future__ import annotations

from datetime import datetime, timezone

from git_reaper import __version__
from git_reaper.models import Provenance, RepoRef


def make_provenance(
    schema: str,
    repo: RepoRef,
    invoked: str,
    generated: str | None = None,
) -> Provenance:
    """Build the stamp. `generated` is injectable so tests stay deterministic;
    it is the only wall-clock value allowed anywhere in an artifact."""
    return Provenance(
        schema=schema,
        source=repo.source,
        ref=repo.ref,
        sha=repo.sha,
        generated=generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        tool_version=__version__,
        invoked=invoked,
    )
