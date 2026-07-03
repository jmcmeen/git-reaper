"""Ward: the composite CI gate.

One `[ward]` table in the grimoire folds the exhume/omens/plague/rot
thresholds (and `distill --check` freshness) into a single policy; one
`reaper ward` returns exit 3 if any ward breaks. A check that *crashes*
counts as broken -- a gate that fails open is no gate at all.

With nothing inscribed, the default policy gates committed secrets only
(`exhume = "any"`), so the command is useful out of the box.
"""

from __future__ import annotations

import time
from typing import Any

from git_reaper.cache import parse_age
from git_reaper.core import distill as distill_core
from git_reaper.core import hygiene, risk
from git_reaper.core import plague as plague_core
from git_reaper.core import rules as rules_core
from git_reaper.core.provenance import make_provenance
from git_reaper.core.source import resolve_source
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import RepoRef, WardCheck, WardResult
from git_reaper.schemas import artifact_schema

_DAY = 86400


def ward(
    repo: RepoRef,
    policy: dict[str, Any],
    policy_source: str = "default",
    rules: list[rules_core.Rule] | None = None,
    weights: dict[str, float] | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper ward",
    generated: str | None = None,
    now: float | None = None,
) -> WardResult:
    """Run every configured ward against the source; the result knows if
    any broke (`result.cursed` drives the exit 3)."""
    backend = backend or default_backend()
    now = time.time() if now is None else now
    result = WardResult(
        provenance=make_provenance(artifact_schema("ward"), repo, invoked, generated),
        policy_source=policy_source,
    )

    def _attempt(name: str, threshold: str, check: Any) -> None:
        try:
            result.checks.append(check())
        except Exception as exc:  # a crashed ward fails closed
            result.checks.append(
                WardCheck(
                    name=name,
                    ok=False,
                    threshold=threshold,
                    detail=f"the check itself failed: {exc}",
                )
            )

    exhume_level = policy.get("exhume", "off")
    if exhume_level != "off":
        _attempt(
            "exhume",
            str(exhume_level),
            lambda: _exhume(repo, backend, rules, str(exhume_level), invoked),
        )
    omens_over = policy.get("omens")
    if omens_over is not None:
        _attempt(
            "omens",
            f"{omens_over:g}",
            lambda: _omens(repo, backend, weights, float(omens_over), invoked, now),
        )
    if policy.get("plague", "off") != "off":
        _attempt("plague", "any", lambda: _plague(repo, invoked))
    rot_age = policy.get("rot")
    if rot_age is not None:
        _attempt("rot", str(rot_age), lambda: _rot(repo, backend, str(rot_age), invoked, now))
    for skill_dir in policy.get("skills", []):
        _attempt("skills", skill_dir, lambda d=skill_dir: _skill(d))

    result.provenance.files = len(result.checks)
    return result


def _exhume(
    repo: RepoRef,
    backend: GitBackend,
    rules: list[rules_core.Rule] | None,
    level: str,
    invoked: str,
) -> WardCheck:
    loaded = rules if rules is not None else rules_core.load_rules()
    found = rules_core.exhume(repo, rules=loaded, backend=backend, invoked=invoked)
    broken = rules_core.cursed(found, level)
    worst = found.findings[0] if found.findings else None
    detail = (
        f"{len(found.findings)} findings"
        + (f"; worst: {worst.rule} in {worst.path}:{worst.line} (masked)" if worst else "")
        if found.findings
        else "the dead kept their secrets"
    )
    return WardCheck(
        name="exhume", ok=not broken, threshold=level, detail=detail, findings=len(found.findings)
    )


def _omens(
    repo: RepoRef,
    backend: GitBackend,
    weights: dict[str, float] | None,
    fail_over: float,
    invoked: str,
    now: float,
) -> WardCheck:
    read = risk.omens(repo, weights=weights, backend=backend, invoked=invoked, now=now)
    doomed = risk.doomed(read, fail_over)
    detail = (
        f"{len(doomed)} files score {fail_over:g} or worse; first: "
        f"{doomed[0].path} ({doomed[0].score:.3f})"
        if doomed
        else f"no omen reaches {fail_over:g}"
    )
    return WardCheck(
        name="omens", ok=not doomed, threshold=f"{fail_over:g}", detail=detail, findings=len(doomed)
    )


def _plague(repo: RepoRef, invoked: str) -> WardCheck:
    checked = plague_core.plague(repo, offline=False, invoked=invoked)
    afflicted = len(checked.afflictions)
    detail = (
        f"{afflicted} afflictions across {len(checked.dependencies)} dependencies"
        if afflicted
        else f"{len(checked.dependencies)} dependencies, none afflicted"
    )
    return WardCheck(
        name="plague", ok=not afflicted, threshold="any", detail=detail, findings=afflicted
    )


def _rot(repo: RepoRef, backend: GitBackend, age: str, invoked: str, now: float) -> WardCheck:
    limit_days = int(parse_age(age) // _DAY)
    report = hygiene.rot(repo, backend=backend, invoked=invoked, now=now)
    rotten = [f for f in report.files if f.age_days > limit_days]
    detail = (
        f"{len(rotten)} files untouched past {limit_days}d; oldest: "
        f"{rotten[0].path} ({rotten[0].age_days}d)"
        if rotten
        else f"nothing untouched past {limit_days}d"
    )
    return WardCheck(name="rot", ok=not rotten, threshold=age, detail=detail, findings=len(rotten))


def _skill(skill_dir: str) -> WardCheck:
    from pathlib import Path

    stamp = distill_core.read_stamp(Path(skill_dir))
    if stamp.sha is None:
        return WardCheck(
            name="skills",
            ok=False,
            threshold=skill_dir,
            detail="the skill carries no sha; re-distill from a git repo",
        )
    current = resolve_source(stamp.source).repo.sha
    if current == stamp.sha:
        return WardCheck(
            name="skills",
            ok=True,
            threshold=skill_dir,
            detail=f"fresh: still speaks for {stamp.source} @ {current[:7]}",
        )
    moved = current[:7] if current else "no repo"
    return WardCheck(
        name="skills",
        ok=False,
        threshold=skill_dir,
        detail=f"stale: distilled at {stamp.sha[:7]}, {stamp.source} is now at {moved}",
        findings=1,
    )
