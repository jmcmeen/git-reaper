"""Prophecy: omens extended across time.

Where omens score the present, prophecy reads the trend: files whose
activity is heating up (this horizon vs the one before it) and whose fixes
keep coming will demand attention next. Framed exactly like omens: hints,
never fate. All age math runs off an injectable `now`.
"""

from __future__ import annotations

import time

from git_reaper.core.history import _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.core.risk import BUGFIX
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import Prophecy, ProphecyResult, RepoRef
from git_reaper.schemas import artifact_schema

_DAY = 86400
DEFAULT_HORIZON_DAYS = 90


def prophecy(
    repo: RepoRef,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    limit: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper prophecy",
    generated: str | None = None,
    now: float | None = None,
) -> ProphecyResult:
    """Forecast which surviving files will demand attention next."""
    if horizon_days <= 0:
        raise ValueError("the horizon must be a positive number of days")
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    now = time.time() if now is None else now
    half_life = float(horizon_days)

    entries: dict[str, Prophecy] = {}
    heats: dict[str, float] = {}
    recent_fixes: dict[str, int] = {}
    for commit in backend.log(root, ref=repo.ref):
        age_days = max(0.0, (now - commit.author_time) / _DAY)
        is_fix = bool(BUGFIX.search(commit.subject))
        recent = age_days <= horizon_days
        prior = horizon_days < age_days <= 2 * horizon_days
        for change in commit.files:
            entry = entries.get(change.path)
            if entry is None:
                entry = entries[change.path] = Prophecy(
                    path=change.path, score=0.0, last_touch=commit.author_date
                )
            entry.commits += 1
            if is_fix:
                entry.bug_commits += 1
                if recent:
                    recent_fixes[change.path] = recent_fixes.get(change.path, 0) + 1
            if recent:
                entry.recent_commits += 1
            elif prior:
                entry.prior_commits += 1
            heats[change.path] = heats.get(change.path, 0.0) + 0.5 ** (age_days / half_life)

    living = [p for p in entries.values() if (root / p.path).is_file()]
    peak_heat = max((heats[p.path] for p in living), default=0.0)
    for entry in living:
        entry.heat = round(heats[entry.path] / peak_heat, 3) if peak_heat else 0.0
        seen = entry.recent_commits + entry.prior_commits
        entry.momentum = round(entry.recent_commits / seen, 3) if seen else 0.0
        entry.bug_momentum = (
            round(recent_fixes.get(entry.path, 0) / entry.recent_commits, 3)
            if entry.recent_commits
            else 0.0
        )
        entry.score = round(0.5 * entry.heat + 0.3 * entry.momentum + 0.2 * entry.bug_momentum, 3)

    living.sort(key=lambda p: (-p.score, p.path))
    if limit is not None:
        living = living[:limit]
    result = ProphecyResult(
        provenance=make_provenance(artifact_schema("prophecy"), repo, invoked, generated),
        horizon_days=horizon_days,
        prophecies=living,
    )
    result.provenance.files = len(living)
    return result
