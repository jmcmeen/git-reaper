"""Scry: gaze between two refs and read what changed.

Graduated from the back of the crypt once omens stabilized. The vision
covers the commits reachable from B but not A (git's A..B range): total
churn, the most-changed files, who did the changing, and which souls
appeared for the first time inside the range.
"""

from __future__ import annotations

from pathlib import Path

from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, GitError, default_backend
from git_reaper.models import AuthorShare, RepoRef, ScryDelta, ScryResult
from git_reaper.schemas import artifact_schema


def scry(
    repo: RepoRef,
    ref_a: str,
    ref_b: str,
    limit: int | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper scry",
    generated: str | None = None,
) -> ScryResult:
    """Compare two refs: churn, files, and contributors in A..B."""
    backend = backend or default_backend()
    root = Path(repo.path)
    if not backend.is_repo(root):
        raise GitError(f"not a git repository: {repo.source} (scrying needs history)")

    commits = backend.log(root, ref=f"{ref_a}..{ref_b}")
    before = backend.log(root, ref=ref_a)
    known = {c.author_email or c.author_name for c in before}

    result = ScryResult(
        provenance=make_provenance(artifact_schema("scry"), repo, invoked, generated),
        ref_a=ref_a,
        ref_b=ref_b,
        commits=len(commits),
    )

    deltas: dict[str, ScryDelta] = {}
    shares: dict[str, AuthorShare] = {}
    fresh: list[str] = []
    for commit in commits:
        key = commit.author_email or commit.author_name
        share = shares.get(key)
        if share is None:
            share = shares[key] = AuthorShare(author=commit.author_name)
        share.commits += 1
        if key not in known:
            known.add(key)
            fresh.append(commit.author_name)
        for change in commit.files:
            delta = deltas.get(change.path)
            if delta is None:
                delta = deltas[change.path] = ScryDelta(path=change.path)
            delta.commits += 1
            delta.insertions += change.insertions or 0
            delta.deletions += change.deletions or 0
            result.insertions += change.insertions or 0
            result.deletions += change.deletions or 0

    ranked = sorted(deltas.values(), key=lambda d: (-(d.insertions + d.deletions), d.path))
    result.files = ranked[:limit] if limit is not None else ranked
    result.souls = sorted(shares.values(), key=lambda s: (-s.commits, s.author.lower()))
    result.new_souls = sorted(set(fresh))
    result.provenance.files = len(result.files)
    return result
