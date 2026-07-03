"""History mining over a single pass of `git log`.

chronicle, souls, haunt, and tombstone are all aggregations over the same
commit-with-churn data; autopsy narrows to one path. Anything that needs the
current time takes an injectable `now` (epoch seconds) so age math stays
deterministic in tests -- the same discipline `make_provenance` uses for its
one wall-clock value.
"""

from __future__ import annotations

import time
from pathlib import Path

from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, GitCommit, GitError, default_backend
from git_reaper.models import (
    AuthorShare,
    AutopsyResult,
    ChangelogSection,
    ChronicleResult,
    CommitEntry,
    HauntResult,
    Hotspot,
    RepoRef,
    Soul,
    SoulsResult,
    TombstoneResult,
)
from git_reaper.schemas import artifact_schema

_DAY = 86400
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _require_repo(repo: RepoRef, backend: GitBackend) -> Path:
    """History commands need real git history; a plain folder has none."""
    path = Path(repo.path)
    if not backend.is_repo(path):
        raise GitError(f"not a git repository: {repo.source} (history needs a repo, not a folder)")
    return path


def _churn(commit: GitCommit) -> tuple[int, int]:
    ins = sum(f.insertions or 0 for f in commit.files)
    dels = sum(f.deletions or 0 for f in commit.files)
    return ins, dels


def _commit_entry(commit: GitCommit) -> CommitEntry:
    ins, dels = _churn(commit)
    return CommitEntry(
        sha=commit.sha,
        author=commit.author_name,
        email=commit.author_email,
        date=commit.author_date,
        message=commit.subject,
        files_changed=len(commit.files),
        insertions=ins,
        deletions=dels,
    )


def _age_days(epoch: int, now: float) -> int:
    return max(0, int((now - epoch) // _DAY))


# --------------------------------------------------------------------------
# chronicle
# --------------------------------------------------------------------------


def chronicle(
    repo: RepoRef,
    changelog: bool = False,
    max_count: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper chronicle",
    generated: str | None = None,
) -> ChronicleResult:
    """Extract commit history, newest first; optionally group it by tag."""
    backend = backend or default_backend()
    _require_repo(repo, backend)
    commits = backend.log(repo=Path(repo.path), ref=repo.ref, max_count=max_count)
    entries = [_commit_entry(c) for c in commits]
    result = ChronicleResult(
        provenance=make_provenance(artifact_schema("chronicle"), repo, invoked, generated),
        commits=entries,
    )
    if changelog:
        result.changelog = _build_changelog(entries, backend, Path(repo.path))
    result.provenance.files = len(entries)
    return result


def _build_changelog(
    entries: list[CommitEntry], backend: GitBackend, path: Path
) -> list[ChangelogSection]:
    """Group commits under the tag that heads their release range.

    A tagged commit is the newest member of its own release; commits newer than
    any tag collect under an 'Unreleased' section (dropped when empty).
    """
    tag_by_sha = {t.sha: t for t in backend.tags(path)}
    sections: list[ChangelogSection] = []
    current = ChangelogSection(tag="Unreleased", date=None)
    for entry in entries:
        tag = tag_by_sha.get(entry.sha)
        if tag is not None:
            if current.commits:
                sections.append(current)
            current = ChangelogSection(tag=tag.name, date=tag.date)
        current.commits.append(entry)
    if current.commits:
        sections.append(current)
    return sections


# --------------------------------------------------------------------------
# souls
# --------------------------------------------------------------------------


def souls(
    repo: RepoRef,
    heatmap: bool = False,
    backend: GitBackend | None = None,
    invoked: str = "reaper souls",
    generated: str | None = None,
) -> SoulsResult:
    """Contributor ledger, a bus-factor estimate, and an optional heatmap."""
    backend = backend or default_backend()
    _require_repo(repo, backend)
    commits = backend.log(repo=Path(repo.path), ref=repo.ref)

    ledger: dict[str, Soul] = {}
    grid = [[0] * 24 for _ in range(7)] if heatmap else None
    for commit in commits:
        key = commit.author_email or commit.author_name
        soul = ledger.get(key)
        if soul is None:
            soul = ledger[key] = Soul(
                name=commit.author_name,
                email=commit.author_email,
                first_seen=commit.author_date,
                last_seen=commit.author_date,
            )
        ins, dels = _churn(commit)
        soul.commits += 1
        soul.insertions += ins
        soul.deletions += dels
        # commits arrive newest-first: the first date seen is the last_seen.
        soul.first_seen = commit.author_date
        if grid is not None:
            weekday, hour = _weekday_hour(commit)
            grid[weekday][hour] += 1

    ranked = sorted(ledger.values(), key=lambda s: (-s.commits, s.name.lower()))
    result = SoulsResult(
        provenance=make_provenance(artifact_schema("souls"), repo, invoked, generated),
        souls=ranked,
        total_commits=len(commits),
        bus_factor=_bus_factor(ranked),
        heatmap=grid,
        witching_hour=_witching_hour(grid) if grid is not None else None,
    )
    result.provenance.files = len(ranked)
    return result


def _weekday_hour(commit: GitCommit) -> tuple[int, int]:
    return weekday_hour(commit.author_date)


def weekday_hour(iso: str) -> tuple[int, int]:
    """Weekday (0=Mon) and hour in the commit's *recorded* timezone.

    Parsed from strict-ISO (e.g. 2026-07-02T02:00:00-04:00) so the grid never
    depends on the machine that runs the reaper. Public because the Seance
    chamber maps heatmap cells back to the commits that lit them.
    """
    # ...THH:MM:SS<offset>; take the wall-clock hour as recorded.
    hour = int(iso[11:13]) if len(iso) >= 13 else 0
    weekday = _iso_weekday(iso)
    return weekday, hour


def _iso_weekday(iso: str) -> int:
    from datetime import date

    year, month, day = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
    return date(year, month, day).weekday()


def _bus_factor(souls_ranked: list[Soul]) -> int:
    """Fewest contributors whose commits cross half the total: the classic
    'how many can we lose before the knowledge is gone' estimate."""
    total = sum(s.commits for s in souls_ranked)
    if total == 0:
        return 0
    running = 0
    for i, soul in enumerate(souls_ranked, start=1):
        running += soul.commits
        if running * 2 > total:
            return i
    return len(souls_ranked)


def _witching_hour(grid: list[list[int]]) -> str | None:
    best, best_cell = 0, None
    for weekday in range(7):
        for hour in range(24):
            if grid[weekday][hour] > best:
                best = grid[weekday][hour]
                best_cell = (weekday, hour)
    if best_cell is None:
        return None
    weekday, hour = best_cell
    return f"{_WEEKDAYS[weekday]} {hour:02d}:00"


# --------------------------------------------------------------------------
# haunt
# --------------------------------------------------------------------------


def haunt(
    repo: RepoRef,
    limit: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper haunt",
    generated: str | None = None,
) -> HauntResult:
    """Rank files by change frequency and churn: the bug-risk proxy."""
    backend = backend or default_backend()
    _require_repo(repo, backend)
    commits = backend.log(repo=Path(repo.path), ref=repo.ref)

    spots: dict[str, Hotspot] = {}
    for commit in commits:
        for change in commit.files:
            spot = spots.get(change.path)
            if spot is None:
                spot = spots[change.path] = Hotspot(path=change.path)
            spot.commits += 1
            spot.insertions += change.insertions or 0
            spot.deletions += change.deletions or 0
            spot.churn = spot.insertions + spot.deletions

    ranked = sorted(spots.values(), key=lambda s: (-s.commits, -s.churn, s.path))
    if limit is not None:
        ranked = ranked[:limit]
    result = HauntResult(
        provenance=make_provenance(artifact_schema("haunt"), repo, invoked, generated),
        hotspots=ranked,
    )
    result.provenance.files = len(ranked)
    return result


# --------------------------------------------------------------------------
# autopsy
# --------------------------------------------------------------------------


def autopsy(
    repo: RepoRef,
    rel_path: str,
    follow: bool = True,
    backend: GitBackend | None = None,
    invoked: str = "reaper autopsy",
    generated: str | None = None,
    now: float | None = None,
) -> AutopsyResult:
    """Deep single-file exam: birth, authors, churn, and blame line-age."""
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    now = time.time() if now is None else now
    commits = backend.file_log(root, rel_path, follow=follow)
    if not commits:
        raise GitError(f"no history for {rel_path!r} (never committed, or wrong path)")

    entries = [_commit_entry(c) for c in commits]
    shares: dict[str, AuthorShare] = {}
    ins = dels = 0
    for commit in commits:
        share = shares.get(commit.author_name)
        if share is None:
            share = shares[commit.author_name] = AuthorShare(author=commit.author_name)
        share.commits += 1
        ci, cd = _churn(commit)
        ins += ci
        dels += cd
    born = commits[-1]  # oldest

    result = AutopsyResult(
        provenance=make_provenance(artifact_schema("autopsy"), repo, invoked, generated),
        path=rel_path,
        exists=(root / rel_path).exists(),
        created=born.author_date,
        created_sha=born.sha,
        commits=len(commits),
        insertions=ins,
        deletions=dels,
        authors=sorted(shares.values(), key=lambda a: (-a.commits, a.author.lower())),
        former_names=backend.rename_history(root, rel_path),
        history=entries,
    )
    _blame_ages(result, backend, root, rel_path, now)
    result.provenance.files = 1
    return result


def _blame_ages(
    result: AutopsyResult, backend: GitBackend, root: Path, rel_path: str, now: float
) -> None:
    """Summarize how ancient the surviving lines are, via blame author-times."""
    blame = backend.blame(root, rel_path)
    if not blame:
        return
    times = sorted(when for _author, when in blame)
    result.blame_lines = len(times)
    result.oldest_line = _iso_from_epoch(times[0])
    result.newest_line = _iso_from_epoch(times[-1])
    median = times[len(times) // 2]
    result.median_age_days = _age_days(median, now)


def _iso_from_epoch(epoch: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# tombstone
# --------------------------------------------------------------------------


def tombstone(
    repo: RepoRef,
    backend: GitBackend | None = None,
    invoked: str = "reaper tombstone",
    generated: str | None = None,
    now: float | None = None,
) -> TombstoneResult:
    """A stats card: born, age, commits, souls, last words, witching hour."""
    backend = backend or default_backend()
    _require_repo(repo, backend)
    commits = backend.log(repo=Path(repo.path), ref=repo.ref)
    if not commits:
        raise GitError(f"no commits to memorialize in {repo.source}")
    now = time.time() if now is None else now

    grid = [[0] * 24 for _ in range(7)]
    authors: set[str] = set()
    for commit in commits:
        authors.add(commit.author_email or commit.author_name)
        weekday, hour = _weekday_hour(commit)
        grid[weekday][hour] += 1

    born, last = commits[-1], commits[0]
    name = Path(repo.path).name or repo.source
    result = TombstoneResult(
        provenance=make_provenance(artifact_schema("tombstone"), repo, invoked, generated),
        name=name,
        born=born.author_date,
        last=last.author_date,
        age_days=_age_days(born.author_time, now),
        commits=len(commits),
        souls=len(authors),
        last_words=last.subject,
        witching_hour=_witching_hour(grid),
    )
    result.provenance.files = len(commits)
    return result
