"""Skill harvesting: distill a repo into the facts an Agent Skill is built from.

`conjure` gives a model this repo's contents; `distill` gives it the ability
to *work* here. It is a recipe over rituals that already exist -- census,
bones, chronicle, souls, haunt, unfinished, and the omens bug-fix signal --
plus tooling detection that lifts real build/test/lint commands from the
repo's own files. Deterministic by default: zero network, zero model calls,
so the output is reproducible and citable like every other artifact.

Freshness is first-class: every skill carries the source and sha it was
distilled from, and `read_stamp` recovers them so `--check` (and CI) can
tell when the code has moved on and the skill has started to lie.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from git_reaper.core import census as census_core
from git_reaper.core import history as history_core
from git_reaper.core import scan as scan_core
from git_reaper.core import skeleton as skeleton_core
from git_reaper.core.provenance import make_provenance
from git_reaper.core.risk import BUGFIX
from git_reaper.gitio import GitBackend, default_backend
from git_reaper.models import (
    CensusResult,
    CommandHint,
    DistillResult,
    Gotcha,
    RepoRef,
    Soul,
)
from git_reaper.schemas import artifact_schema

PROFILES = ("repo", "stack", "onboarding")

#: How many hotspots make gotchas.md and how many souls make ownership.md.
DEFAULT_LIMIT = 15

#: Conventional-commit prefixes worth counting as the house style.
_PREFIX = re.compile(r"^(feat|fix|chore|docs|refactor|test|style|perf|build|ci)(\(.+\))?!?:")

#: Words too common in fix subjects to count as a theme.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "bug", "by", "fix", "fixed",
    "fixes", "for", "from", "in", "is", "it", "its", "not", "now", "of", "on",
    "or", "that", "the", "this", "to", "was", "when", "with",
})  # fmt: skip

#: Config files whose presence names the tooling in conventions.md.
_TOOLING_FILES = (
    "pyproject.toml",
    "setup.py",
    "package.json",
    "Makefile",
    "Cargo.toml",
    "go.mod",
    ".pre-commit-config.yaml",
    "ruff.toml",
    ".ruff.toml",
    ".flake8",
    "mypy.ini",
    "tox.ini",
    "pytest.ini",
    ".eslintrc.json",
    ".eslintrc.js",
    ".prettierrc",
    "tsconfig.json",
    "Dockerfile",
    "docker-compose.yml",
    "mkdocs.yml",
    ".editorconfig",
)


class SkillError(ValueError):
    """A skill bundle is missing or its stamp cannot be read."""


@dataclass(frozen=True)
class SkillStamp:
    """The provenance a skill was distilled from, recovered from SKILL.md."""

    source: str
    sha: str | None
    profile: str


def derive_name(repo: RepoRef) -> str:
    """A skill's name from its source: the directory or repo it was reaped from."""
    tail = repo.source.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    if tail in ("", "."):
        tail = Path(repo.path).name
    return tail or "skill"


def distill(
    repo: RepoRef,
    profile: str = "repo",
    anon: bool = False,
    limit: int = DEFAULT_LIMIT,
    excludes: list[str] | None = None,
    backend: GitBackend | None = None,
    invoked: str = "reaper distill",
    generated: str | None = None,
) -> DistillResult:
    """Compose the existing rituals into one distilled picture of the repo."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r} (use {', '.join(PROFILES)})")
    backend = backend or default_backend()
    root = Path(repo.path)

    census = census_core.census(repo, excludes=excludes, invoked=invoked, generated=generated)
    bones = skeleton_core.bones(repo, excludes=excludes, invoked=invoked, generated=generated)
    unfinished = scan_core.unfinished(
        repo, excludes=excludes, invoked=invoked, generated=generated, backend=backend
    )
    chronicle = history_core.chronicle(repo, backend=backend, invoked=invoked, generated=generated)
    souls = history_core.souls(repo, backend=backend, invoked=invoked, generated=generated)
    haunt = history_core.haunt(repo, backend=backend, invoked=invoked, generated=generated)

    fixes_by_path = _bugfix_counts(repo, backend)
    gotchas = [
        Gotcha(
            path=spot.path,
            commits=spot.commits,
            bug_commits=fixes_by_path.get(spot.path, 0),
            churn=spot.churn,
        )
        for spot in haunt.hotspots[:limit]
    ]

    prefixes: Counter[str] = Counter()
    for entry in chronicle.commits:
        match = _PREFIX.match(entry.message)
        if match:
            prefixes[match.group(1)] += 1
    sampled = len(chronicle.commits)
    conventional = sum(prefixes.values()) / sampled if sampled else 0.0

    owners = souls.souls[:limit]
    if anon:
        owners = [
            Soul(
                name=f"keeper {i}",
                email="",
                commits=s.commits,
                insertions=s.insertions,
                deletions=s.deletions,
                first_seen=s.first_seen,
                last_seen=s.last_seen,
            )
            for i, s in enumerate(owners, start=1)
        ]

    name = derive_name(repo)
    result = DistillResult(
        provenance=make_provenance(artifact_schema("distill"), repo, invoked, generated),
        name=name,
        profile=profile,
        description=_description(name, census, profile),
        languages=census.extensions,
        total_files=census.total_files,
        layout=_layout(root),
        tooling=[f for f in _TOOLING_FILES if (root / f).exists()],
        commands=_commands(root),
        commits_sampled=sampled,
        commit_prefixes=dict(prefixes.most_common()),
        conventional_share=round(conventional, 3),
        gotchas=gotchas,
        bug_themes=_bug_themes(repo, backend),
        marker_counts=unfinished.counts,
        owners=owners,
        bus_factor=souls.bus_factor,
        bones=bones,
    )
    result.provenance.files = census.total_files
    result.provenance.token_estimate = census.token_estimate
    return result


def _description(name: str, census: CensusResult, profile: str) -> str:
    tongues = [s.language for s in census.extensions if s.language][:3]
    spoken = "/".join(dict.fromkeys(tongues)) or "mixed"
    if profile == "stack":
        return f"Working idioms for the {spoken} stack, distilled from {name}."
    if profile == "onboarding":
        return f"A new-contributor guide to {name} ({spoken})."
    return f"Conventions, commands, structure, and gotchas for working in {name} ({spoken})."


def _layout(root: Path) -> list[str]:
    """Top-level entries, dirs first, the hidden and the interred skipped."""
    dirs: list[str] = []
    files: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith(".") or entry.name in ("node_modules", "__pycache__"):
            continue
        (dirs if entry.is_dir() else files).append(
            f"{entry.name}/" if entry.is_dir() else entry.name
        )
    return dirs + files


def _bugfix_counts(repo: RepoRef, backend: GitBackend) -> dict[str, int]:
    """Per-file bug-fix commit counts, via the same regex omens uses."""
    counts: Counter[str] = Counter()
    for commit in backend.log(Path(repo.path), ref=repo.ref):
        if BUGFIX.search(commit.subject):
            for change in commit.files:
                counts[change.path] += 1
    return dict(counts)


def _bug_themes(repo: RepoRef, backend: GitBackend, top: int = 10) -> dict[str, int]:
    """Recurring words in bug-fix subjects: the failure themes that repeat."""
    words: Counter[str] = Counter()
    for commit in backend.log(Path(repo.path), ref=repo.ref):
        if not BUGFIX.search(commit.subject):
            continue
        for word in re.findall(r"[a-z][a-z0-9_-]{2,}", commit.subject.lower()):
            if word not in _STOPWORDS:
                words[word] += 1
    return {word: n for word, n in words.most_common(top) if n > 1}


# --------------------------------------------------------------------------
# tooling detection: real commands, lifted from the repo's own files
# --------------------------------------------------------------------------

_MAKE_KINDS = {
    "build": "build",
    "test": "test",
    "tests": "test",
    "check": "test",
    "lint": "lint",
    "format": "format",
    "fmt": "format",
    "run": "run",
    "serve": "run",
    "dev": "run",
    "docs": "docs",
}

_NPM_KINDS = {
    "build": "build",
    "test": "test",
    "lint": "lint",
    "format": "format",
    "start": "run",
    "dev": "run",
    "serve": "run",
    "docs": "docs",
}


def _commands(root: Path) -> list[CommandHint]:
    hints: list[CommandHint] = []
    hints += _pyproject_commands(root / "pyproject.toml")
    hints += _makefile_commands(root / "Makefile")
    hints += _package_json_commands(root / "package.json")
    hints += _workflow_commands(root / ".github" / "workflows")
    seen: set[str] = set()
    unique = []
    for hint in hints:
        if hint.command not in seen:
            seen.add(hint.command)
            unique.append(hint)
    return unique


def _pyproject_commands(path: Path) -> list[CommandHint]:
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return []
    hints: list[CommandHint] = []
    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        tool = {}
    if "pytest" in tool or (path.parent / "tests").is_dir():
        hints.append(CommandHint(kind="test", command="pytest", origin=path.name))
    if "ruff" in tool:
        hints.append(CommandHint(kind="lint", command="ruff check .", origin=path.name))
        hints.append(CommandHint(kind="format", command="ruff format .", origin=path.name))
    if "mypy" in tool:
        hints.append(CommandHint(kind="lint", command="mypy .", origin=path.name))
    scripts = data.get("project", {}).get("scripts", {})
    if isinstance(scripts, dict):
        for name in sorted(scripts):
            hints.append(CommandHint(kind="run", command=str(name), origin=path.name))
    return hints


def _makefile_commands(path: Path) -> list[CommandHint]:
    if not path.is_file():
        return []
    hints: list[CommandHint] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^([A-Za-z][\w-]*):(?!=)", line)
        if not match:
            continue
        target = match.group(1)
        if target == ".PHONY":
            continue
        kind = _MAKE_KINDS.get(target, "other")
        hints.append(CommandHint(kind=kind, command=f"make {target}", origin="Makefile"))
    return hints


def _package_json_commands(path: Path) -> list[CommandHint]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return []
    return [
        CommandHint(
            kind=_NPM_KINDS.get(name, "other"),
            command=f"npm run {name}",
            origin="package.json",
        )
        for name in sorted(scripts)
    ]


def _workflow_commands(workflows: Path) -> list[CommandHint]:
    """`run:` one-liners from CI workflows: what the build actually executes."""
    if not workflows.is_dir():
        return []
    hints: list[CommandHint] = []
    for path in sorted(workflows.glob("*.y*ml")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^\s*(?:-\s+)?run:\s+(\S.*)$", line)
            if not match:
                continue
            command = match.group(1).strip()
            if command in ("|", ">") or command.startswith(("|", ">")):
                continue  # multi-line scripts are CI plumbing, not a recipe
            kind = "other"
            for probe, k in (
                ("lint", "lint"),
                ("ruff", "lint"),
                ("eslint", "lint"),
                ("mypy", "lint"),
                ("test", "test"),
                ("build", "build"),
            ):
                if probe in command:
                    kind = k
                    break
            hints.append(CommandHint(kind=kind, command=command, origin=f"ci: {path.name}"))
    return hints


# --------------------------------------------------------------------------
# freshness: the stamp a skill carries, and how to read it back
# --------------------------------------------------------------------------

_STAMP_LINE = re.compile(r"^(source|sha|profile):\s+(.*)$")


def read_stamp(skill_dir: Path) -> SkillStamp:
    """Recover the source, sha, and profile a skill was distilled from."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SkillError(f"no SKILL.md under {skill_dir}; point --check at a skill directory")
    found: dict[str, str] = {}
    for line in skill_md.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _STAMP_LINE.match(line.strip())
        if match:
            found.setdefault(match.group(1), match.group(2).strip())
    if "source" not in found:
        raise SkillError(f"{skill_md} carries no distill stamp; re-run `reaper distill`")
    sha = found.get("sha")
    return SkillStamp(
        source=found["source"],
        sha=None if sha in (None, "", "unknown") else sha,
        profile=found.get("profile", "repo"),
    )


# --------------------------------------------------------------------------
# polish: the optional pass through the caller's own model
# --------------------------------------------------------------------------

#: The stamp closes here; everything before it is protected from the polisher.
_STAMP_CLOSE = "\n-->\n"


def polish_bundle(bundle: dict[str, str], command: str) -> dict[str, str]:
    """Pipe each draft's prose through the caller's own command, stdin to stdout.

    The default distill path never needs a key; this is the opt-in escape
    hatch. The model lives on the caller's side (the same principle that
    retired ouija), so `command` is whatever they trust -- `claude -p ...`,
    a local model, `fmt`. Frontmatter and the provenance stamp are held
    back and reattached: a polisher may smooth prose, never facts of origin.
    """
    argv = shlex.split(command)
    if not argv:
        raise SkillError("--polish needs a command that reads stdin and writes stdout")
    polished: dict[str, str] = {}
    for rel in sorted(bundle):
        head, body = _split_stamp(bundle[rel])
        try:
            proc = subprocess.run(argv, input=body, capture_output=True, text=True)
        except OSError as exc:
            raise SkillError(f"polish command failed to start: {exc}") from exc
        if proc.returncode != 0:
            detail = proc.stderr.strip().splitlines()
            hint = f": {detail[-1]}" if detail else ""
            raise SkillError(f"polish failed on {rel} (exit {proc.returncode}){hint}")
        if not proc.stdout.strip():
            raise SkillError(f"polish returned nothing for {rel}; keeping drafts unwritten")
        out = proc.stdout if proc.stdout.endswith("\n") else proc.stdout + "\n"
        polished[rel] = head + out
    return polished


def _split_stamp(content: str) -> tuple[str, str]:
    """Split a draft into (frontmatter + provenance stamp, prose body)."""
    idx = content.find(_STAMP_CLOSE)
    if idx == -1:
        return "", content
    cut = idx + len(_STAMP_CLOSE)
    return content[:cut], content[cut:]
