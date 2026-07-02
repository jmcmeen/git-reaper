"""Omens: a composite risk prophecy per file.

The score blends four classic proxies - churn, bug-fix density, recency,
and size - each normalized to 0..1, weighted by the grimoire's [omens]
table. Lenses isolate one component (`--lens churn`) or blend them all.

Honest framing, per the plan: omens are hints, not fate. A high score says
"look here first", never "this file is broken".
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from git_reaper.config import DEFAULT_OMEN_WEIGHTS
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, GitError, default_backend
from git_reaper.models import Omen, OmensResult, RepoRef
from git_reaper.schemas import artifact_schema

LENSES = ("all", "churn", "bugs", "age", "size")

#: Commit messages that smell like a bug being fixed.
_BUGFIX = re.compile(r"(?i)\b(fix(e[sd])?|bug|defect|fault|hotfix|patch|repair|regression)\b")

_DAY = 86400
#: Recency half-life: a file untouched for 90 days is half as "hot".
_HALF_LIFE_DAYS = 90.0


def omens(
    repo: RepoRef,
    lens: str = "all",
    weights: dict[str, float] | None = None,
    limit: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper omens",
    generated: str | None = None,
    now: float | None = None,
) -> OmensResult:
    """Score every surviving file and rank the cursed ones first."""
    if lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r} (use {', '.join(LENSES)})")
    backend = backend or default_backend()
    root = Path(repo.path)
    if not backend.is_repo(root):
        raise GitError(f"not a git repository: {repo.source} (omens read history)")
    weights = dict(weights or DEFAULT_OMEN_WEIGHTS)
    now = time.time() if now is None else now

    commits = backend.log(root, ref=repo.ref)
    entries: dict[str, Omen] = {}
    last_touch: dict[str, int] = {}
    for commit in commits:
        is_fix = bool(_BUGFIX.search(commit.subject))
        for change in commit.files:
            omen = entries.get(change.path)
            if omen is None:
                omen = entries[change.path] = Omen(path=change.path, score=0.0)
            omen.commits += 1
            omen.churn += (change.insertions or 0) + (change.deletions or 0)
            if is_fix:
                omen.bug_commits += 1
            # commits arrive newest first; the first sighting is the latest.
            if change.path not in last_touch:
                last_touch[change.path] = commit.author_time

    # Only prophesy over files that still exist; the dead are graveyard business.
    living = [omen for omen in entries.values() if (root / omen.path).is_file()]
    for omen in living:
        omen.size_bytes = (root / omen.path).stat().st_size
        omen.age_days = max(0, int((now - last_touch[omen.path]) // _DAY))

    _score(living, weights, lens)
    living.sort(key=lambda o: (-o.score, o.path))
    if limit is not None:
        living = living[:limit]

    result = OmensResult(
        provenance=make_provenance(artifact_schema("omens"), repo, invoked, generated),
        lens=lens,
        weights={k: weights[k] for k in sorted(weights)},
        omens=living,
    )
    result.provenance.files = len(living)
    return result


def _score(omens_list: list[Omen], weights: dict[str, float], lens: str) -> None:
    """Fill per-component scores (0..1) and the composite."""
    max_churn = max((o.churn for o in omens_list), default=0)
    max_bugs = max((o.bug_commits for o in omens_list), default=0)
    max_size = max((o.size_bytes for o in omens_list), default=0)
    for omen in omens_list:
        omen.churn_score = round(omen.churn / max_churn, 3) if max_churn else 0.0
        omen.bug_score = round(omen.bug_commits / max_bugs, 3) if max_bugs else 0.0
        omen.age_score = round(0.5 ** (omen.age_days / _HALF_LIFE_DAYS), 3)
        omen.size_score = round(omen.size_bytes / max_size, 3) if max_size else 0.0
        if lens == "all":
            total = sum(weights.values())
            omen.score = round(
                (
                    weights["churn"] * omen.churn_score
                    + weights["bugs"] * omen.bug_score
                    + weights["age"] * omen.age_score
                    + weights["size"] * omen.size_score
                )
                / total,
                3,
            )
        else:
            omen.score = {
                "churn": omen.churn_score,
                "bugs": omen.bug_score,
                "age": omen.age_score,
                "size": omen.size_score,
            }[lens]


def doomed(result: OmensResult, fail_over: float) -> list[Omen]:
    """The omens at or above the CI threshold (exit 3 when non-empty)."""
    return [omen for omen in result.omens if omen.score >= fail_over]
