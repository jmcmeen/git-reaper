"""Wake: draft a Keep-a-Changelog section from the commits since the last tag.

The reaper recounts the deeds at the wake. Conventional-commit prefixes map
onto the Keep-a-Changelog categories; everything unprefixed lands under
Changed, honestly labeled a draft for a human to edit. Dogfoodable: this
project's own changelog sections start life as `reaper wake` output.
"""

from __future__ import annotations

import re

from git_reaper.core.history import _commit_entry, _require_repo
from git_reaper.core.provenance import make_provenance
from git_reaper.gitio import GitBackend, GitError, default_backend
from git_reaper.models import RepoRef, WakeResult, WakeSection
from git_reaper.schemas import artifact_schema

#: Keep-a-Changelog's categories, in its canonical order.
SECTION_ORDER = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

_PREFIX = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]*\))?(?P<bang>!)?:\s")

_TYPE_TO_SECTION = {
    "feat": "Added",
    "add": "Added",
    "fix": "Fixed",
    "bug": "Fixed",
    "hotfix": "Fixed",
    "remove": "Removed",
    "revert": "Removed",
    "deprecate": "Deprecated",
    "security": "Security",
    "sec": "Security",
}


def _classify(subject: str) -> tuple[str, bool]:
    """(section title, is-breaking) for one commit subject."""
    match = _PREFIX.match(subject)
    if not match:
        return "Changed", "BREAKING" in subject
    breaking = bool(match.group("bang"))
    section = _TYPE_TO_SECTION.get(match.group("type").lower(), "Changed")
    return section, breaking


def wake(
    repo: RepoRef,
    since: str | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper wake",
    generated: str | None = None,
) -> WakeResult:
    """Gather the commits since the last tag (or `since`) into a draft.

    With no tags and no `since`, the wake covers the whole history -- the
    first release deserves a changelog too.
    """
    backend = backend or default_backend()
    root = _require_repo(repo, backend)
    commits = backend.log(root, ref=repo.ref)

    since_name, since_date = "", ""
    boundary_shas: set[str] = set()
    if since is not None:
        anchored = backend.log(root, ref=since, max_count=1)
        if not anchored:
            raise GitError(f"unknown ref {since!r}; `reaper chronicle` shows the history")
        boundary_shas = {anchored[0].sha}
        since_name, since_date = since, anchored[0].author_date
    else:
        tags = backend.tags(root)
        tagged = {t.sha: t for t in tags}
        for commit in commits:
            tag = tagged.get(commit.sha)
            if tag is not None:
                boundary_shas = {tag.sha}
                since_name, since_date = tag.name, tag.date
                break

    fresh = []
    for commit in commits:
        if commit.sha in boundary_shas:
            break
        fresh.append(commit)

    sections = {title: WakeSection(title=title) for title in SECTION_ORDER}
    any_breaking = False
    for commit in fresh:
        title, breaking = _classify(commit.subject)
        any_breaking = any_breaking or breaking
        sections[title].entries.append(_commit_entry(commit))

    kept = [sections[title] for title in SECTION_ORDER if sections[title].entries]
    result = WakeResult(
        provenance=make_provenance(artifact_schema("wake"), repo, invoked, generated),
        since=since_name,
        since_date=since_date,
        suggested_bump=_bump(kept, any_breaking),
        commits=len(fresh),
        sections=kept,
    )
    result.provenance.files = len(fresh)
    return result


def _bump(sections: list[WakeSection], breaking: bool) -> str:
    if breaking:
        return "major"
    titles = {s.title for s in sections}
    if "Added" in titles or "Removed" in titles:
        return "minor"
    if titles:
        return "patch"
    return "none"
