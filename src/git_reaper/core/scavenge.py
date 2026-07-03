"""Scavenging: lift existing Agent Skill folders out of a repository.

`distill` writes a new skill from what it learns about a repo; `scavenge`
steals the ones already interred there - any folder holding a SKILL.md,
taken whole (references, scripts, binary assets and all) and reburied in
a library directory. A routing SKILL.md at the library root indexes the
loot, so a scavenged crypt is itself loadable - and `necropolis scavenge`
composes into a fleet-wide library with two levels of routing.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from git_reaper import fsutil, schemas
from git_reaper.core.provenance import make_provenance
from git_reaper.ignore import IgnoreMatcher
from git_reaper.models import RepoRef, ScavengedSkill, ScavengeResult

#: The file that marks a folder as an Agent Skill.
MARKER = "SKILL.md"

_DESCRIPTION = re.compile(r'^description:\s*"?(.*?)"?\s*$')


def skill_description(skill_md: Path) -> str:
    """A skill's own frontmatter description, escaped for the table cells
    every caller puts it in (pipes and newlines would corrupt them)."""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines()[:10]:  # frontmatter lives at the top
        match = _DESCRIPTION.match(line)
        if match:
            return match.group(1).replace("|", "\\|").strip()
    return ""


def find_skills(root: Path, matcher: IgnoreMatcher) -> list[str]:
    """POSIX-relative paths of every skill folder: dirs holding a SKILL.md.

    Topmost wins: a skill folder travels whole, so a SKILL.md nested inside
    another skill's folder rides along instead of being lifted twice.
    """
    found: list[str] = []

    def _walk(directory: Path) -> None:
        rel = "." if directory == root else directory.relative_to(root).as_posix()
        marker_rel = MARKER if rel == "." else f"{rel}/{MARKER}"
        if (directory / MARKER).is_file() and not matcher.ignored(marker_rel):
            found.append(rel)
            return
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.is_symlink() or not entry.is_dir():
                continue
            if matcher.ignored(entry.relative_to(root).as_posix(), is_dir=True):
                continue
            _walk(entry)

    _walk(root)
    return found


def _source_name(source: str) -> str:
    """The source's last path segment, .git shroud removed (fleet.derive_name
    stays in fleet; fleet imports from here, so the two lines live twice)."""
    tail = re.split(r"[\\/]", source.rstrip("\\/"))[-1]
    return tail.removesuffix(".git") or "skill"


def _copy_skill(src: Path, dest: Path, root: Path, matcher: IgnoreMatcher) -> int:
    """Copy one skill folder byte-for-byte, honoring ignore rules; the file count."""
    copied = 0

    def _walk(directory: Path) -> None:
        nonlocal copied
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.is_symlink():  # a grave's symlink points anywhere; leave it
                continue
            rel = entry.relative_to(root).as_posix()
            if matcher.ignored(rel, is_dir=entry.is_dir()):
                continue
            target = dest / entry.relative_to(src)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                _walk(entry)
            elif entry.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, target)  # bytes, not text: binaries survive
                copied += 1

    _walk(src)
    return copied


def scavenge(
    repo: RepoRef,
    out_dir: Path,
    excludes: list[str] | None = None,
    invoked: str = "reaper scavenge",
    generated: str | None = None,
) -> ScavengeResult:
    """Lift every skill folder out of the repo into out_dir, and index the loot.

    Re-scavenging refreshes: a skill already in the crypt under the same name
    is replaced, not numbered. Numbering only separates two skills that share
    a folder name within one repo. Finding nothing writes nothing.
    """
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = ScavengeResult(
        provenance=make_provenance(schemas.artifact_schema("scavenge"), repo, invoked, generated),
        out=str(out_dir),
    )
    rels = find_skills(root, matcher)
    if not rels:
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    taken: set[str] = {MARKER}  # the routing index's own name is never loot
    for rel in rels:
        base = _source_name(repo.source) if rel == "." else rel.rsplit("/", 1)[-1]
        name, n = base, 2
        while name in taken:
            name, n = f"{base}-{n}", n + 1
        taken.add(name)
        dest = out_dir / name
        if dest.exists():
            fsutil.force_rmtree(dest)
        src = root if rel == "." else root / rel
        copied = _copy_skill(src, dest, root, matcher)
        result.skills.append(
            ScavengedSkill(
                name=name,
                path=rel,
                description=skill_description(src / MARKER),
                files=copied,
            )
        )

    (out_dir / MARKER).write_text(render_crypt_skill(result, out_dir), encoding="utf-8")
    return result


def render_crypt_skill(result: ScavengeResult, out_dir: Path) -> str:
    """The routing skill at the crypt's root: one row per scavenged skill.

    An agent loads this first and follows a row to the skill it needs; each
    description is the skill's own. `necropolis scavenge` reads this file's
    description back for its fleet-level index, so the levels compose.
    """
    name = out_dir.name or "skill-crypt"
    count = len(result.skills)
    skills = "skill" if count == 1 else "skills"
    lines = [
        "---",
        f"name: {name}",
        f'description: "A skill crypt: {count} {skills} scavenged from '
        f'{result.provenance.source}. Load this first, then follow the table."',
        "---",
        "",
        f"# Skill crypt: {name}",
        "",
        f"Skills lifted whole from `{result.provenance.source}`. Find the one you",
        "need below and load its `SKILL.md`.",
        "",
        "| skill | taken from | what it teaches |",
        "| --- | --- | --- |",
    ]
    for skill in result.skills:
        lines.append(
            f"| [{skill.name}]({skill.name}/{MARKER}) | {skill.path} | {skill.description} |"
        )
    return "\n".join(lines) + "\n"
