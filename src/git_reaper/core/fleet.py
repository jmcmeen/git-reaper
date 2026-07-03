"""The necropolis: fan one reaper command across every grave in a manifest.

Graves come from a `necropolis.toml` manifest or, with `--org`, from the
`gh` CLI. Each grave gets its own artifact in the out dir; a combined
INDEX.md records every outcome, including the failures - a fan-out that
hides a failed grave is worse than none.

The runner is injectable: the CLI passes a closure that re-invokes the
Typer app (the same trick `cast` uses), and tests pass a fake.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from git_reaper.models import GraveOutcome, NecropolisResult

MANIFEST = "necropolis.toml"

#: (argv for the reaper app) -> exit code. 0 rest in peace, 3 cursed.
Runner = Callable[[list[str]], int]

_FORMAT_EXT = {"md": ".md", "json": ".json", "csv": ".csv", "html": ".html"}

#: Commands whose --out is a directory bundle (one skill per grave), not a file.
BUNDLE_COMMANDS = frozenset({"distill"})


class FleetError(ValueError):
    """The manifest is miswritten or the org lookup failed."""


@dataclass(frozen=True)
class Grave:
    """One repo in the necropolis."""

    name: str
    source: str
    tags: tuple[str, ...] = ()


def load_manifest(path: Path) -> list[Grave]:
    """Parse necropolis.toml: [[grave]] tables with source, name?, tags?."""
    if not path.is_file():
        raise FleetError(f"no manifest at {path}; write [[grave]] tables into {MANIFEST}")
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise FleetError(f"{path} is not valid TOML: {exc}") from exc
    entries = data.get("grave", [])
    if not isinstance(entries, list) or not entries:
        raise FleetError(f"{path}: no [[grave]] tables found")
    graves: list[Grave] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str):
            raise FleetError(f"{path}: grave #{i} needs a string 'source'")
        source = entry["source"]
        name = str(entry.get("name") or derive_name(source))
        if name in seen:
            raise FleetError(f"{path}: duplicate grave name {name!r}; set distinct 'name' keys")
        seen.add(name)
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise FleetError(f"{path}: grave {name!r} 'tags' must be a list of strings")
        graves.append(Grave(name=name, source=source, tags=tuple(tags)))
    return graves


def derive_name(source: str) -> str:
    """A grave's name from its source: last path segment, .git shroud removed."""
    tail = source.rstrip("/").rsplit("/", 1)[-1]
    return tail.removesuffix(".git") or "grave"


def org_graves(org: str, limit: int = 200) -> list[Grave]:
    """Every repo in a GitHub org, via the gh CLI (which owns the auth)."""
    gh = shutil.which("gh")
    if gh is None:
        raise FleetError("--org needs the `gh` CLI on PATH (https://cli.github.com)")
    proc = subprocess.run(
        [gh, "repo", "list", org, "--limit", str(limit), "--json", "name,url"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FleetError(f"gh repo list {org} failed: {proc.stderr.strip()}")
    try:
        entries = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise FleetError(f"gh returned unparseable JSON: {exc}") from exc
    return [Grave(name=e["name"], source=e["url"]) for e in entries]


def artifact_extension(args: list[str]) -> str:
    """Match the per-grave artifact suffix to any --format in the args."""
    for i, arg in enumerate(args):
        if arg in ("--format", "-f") and i + 1 < len(args):
            return _FORMAT_EXT.get(args[i + 1], ".md")
        if arg.startswith("--format="):
            return _FORMAT_EXT.get(arg.split("=", 1)[1], ".md")
    return ".md"


def necropolis(
    command: str,
    args: list[str],
    graves: list[Grave],
    out_dir: Path,
    runner: Runner,
    tag: str | None = None,
) -> NecropolisResult:
    """Run `reaper <command> <grave> <args> --out <dir>/<name>.<ext>` per grave."""
    chosen = [g for g in graves if tag is None or tag in g.tags]
    result = NecropolisResult(command=command)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = artifact_extension(args)
    bundle = command in BUNDLE_COMMANDS

    for grave in chosen:
        artifact = out_dir / grave.name if bundle else out_dir / f"{grave.name}{ext}"
        outcome = GraveOutcome(name=grave.name, source=grave.source, artifact=str(artifact))
        try:
            code = runner([command, grave.source, *args, "--out", str(artifact)])
        except Exception as exc:  # a grave must never take the fleet down with it
            outcome.ok = False
            outcome.exit_code = 1
            outcome.error = str(exc)
        else:
            outcome.exit_code = code
            outcome.ok = code == 0
            if code == 3:
                outcome.error = "cursed: the scan found what you feared"
            elif code != 0:
                outcome.error = f"the ritual failed (exit {code})"
        if not (artifact.is_dir() if bundle else artifact.is_file()):
            outcome.artifact = ""
        result.graves.append(outcome)

    index = out_dir / "INDEX.md"
    index.write_text(render_index(result), encoding="utf-8")
    result.index = str(index)
    if bundle:
        (out_dir / "SKILL.md").write_text(render_index_skill(result, out_dir), encoding="utf-8")
    return result


def render_index(result: NecropolisResult) -> str:
    """The combined index: one row per grave, failures included."""
    lines = [
        f"# necropolis: reaper {result.command}",
        "",
        "| grave | source | fate | artifact |",
        "| --- | --- | --- | --- |",
    ]
    for outcome in result.graves:
        if outcome.ok:
            fate = "rest in peace"
        elif outcome.exit_code == 3:
            fate = "cursed"
        else:
            fate = outcome.error or "failed"
        artifact = Path(outcome.artifact).name if outcome.artifact else "-"
        lines.append(f"| {outcome.name} | {outcome.source} | {fate} | {artifact} |")
    reaped = sum(1 for o in result.graves if o.ok)
    lines.append("")
    lines.append(f"{reaped} of {len(result.graves)} graves reaped")
    return "\n".join(lines) + "\n"


_DESCRIPTION = re.compile(r'^description:\s*"?(.*?)"?\s*$')


def _skill_description(skill_md: Path) -> str:
    """A skill's own description line, read back from its frontmatter."""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines()[:10]:  # frontmatter lives at the top
        match = _DESCRIPTION.match(line)
        if match:
            return match.group(1)
    return ""


def render_index_skill(result: NecropolisResult, out_dir: Path) -> str:
    """The routing skill at the library's root: one row per harvested skill.

    An agent loads this first and follows the row to the right repo's skill;
    each row's description is read back from the skill it routes to.
    """
    name = out_dir.name or "skill-library"
    reaped = [o for o in result.graves if o.ok and o.artifact]
    repos = "repository" if len(reaped) == 1 else "repositories"
    lines = [
        "---",
        f"name: {name}",
        f'description: "A skill library: {len(reaped)} {repos} distilled, one skill '
        'each. Load this first, then follow the table to the right one."',
        "---",
        "",
        f"# Skill library: {name}",
        "",
        "One skill per repository. Find the repo you are working in below and load",
        "its `SKILL.md`; everything in it was distilled from that repo itself.",
        "",
        "| skill | source | what it teaches |",
        "| --- | --- | --- |",
    ]
    for outcome in reaped:
        description = _skill_description(Path(outcome.artifact) / "SKILL.md")
        lines.append(
            f"| [{outcome.name}]({outcome.name}/SKILL.md) | {outcome.source} | {description} |"
        )
    missing = [o for o in result.graves if not (o.ok and o.artifact)]
    if missing:
        lines.append("")
        lines.append(
            "Not harvested (the fan-out failed there): " + ", ".join(o.name for o in missing) + "."
        )
    return "\n".join(lines) + "\n"


def fleet_exit_code(result: NecropolisResult) -> int:
    """1 if any grave failed outright, else 3 if any is cursed, else 0."""
    codes = {outcome.exit_code for outcome in result.graves}
    if codes - {0, 3}:
        return 1
    if 3 in codes:
        return 3
    return 0
