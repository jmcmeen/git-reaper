"""Markdown rendering: provenance blocks, harvest artifacts, tree listings.

Harvest artifacts are streamed: file contents are read chunk by chunk while
writing, so peak memory is bounded by a chunk, not the repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from git_reaper.fsutil import human_size
from git_reaper.models import (
    AutopsyResult,
    BloatResult,
    BonesResult,
    CensusResult,
    ChronicleResult,
    DoppelgangersResult,
    ExhumeResult,
    GhostsResult,
    GraveyardResult,
    HarvestResult,
    HauntResult,
    OmensResult,
    PlagueResult,
    Provenance,
    RotResult,
    ScryResult,
    SoulsResult,
    TombstoneResult,
    TreeNode,
    TreeResult,
    UnfinishedResult,
    VeilResult,
)

_CHUNK = 65536
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _cell(text: str) -> str:
    """Make a string safe for a markdown table cell (pipes, newlines)."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_provenance(prov: Provenance, kind: str, extra: list[str] | None = None) -> str:
    """The header block every combined artifact opens with.

    `extra` lines (e.g. "part: 2/5" on conjure shards) land before the close.
    """
    lines = [
        "<!--",
        f"git-reaper {kind}",
        f"schema:    {prov.schema}",
        f"source:    {prov.source}",
    ]
    if prov.ref or prov.sha:
        ref = prov.ref or "HEAD"
        at = f" @ {prov.sha[:7]}" if prov.sha else ""
        lines.append(f"ref:       {ref}{at}")
    lines += [
        f"generated: {prov.generated}",
        f"tool:      git-reaper {prov.tool_version}",
        f"invoked:   {prov.invoked}",
        f"files:     {prov.files}   tokens: ~{prov.token_estimate:,} (chars/4)",
    ]
    lines += extra or []
    lines.append("-->")
    return "\n".join(lines) + "\n"


def write_harvest(result: HarvestResult, out: IO[str]) -> None:
    """Stream the concatenated artifact: provenance, then each file wrapped
    in the stable, greppable delimiters from the plan."""
    out.write(render_provenance(result.provenance, "harvest"))
    root = Path(result.root)
    for entry in result.files:
        out.write(f"\n## {entry.path}\n\n")
        with (root / entry.path).open("r", encoding="utf-8", errors="replace") as fh:
            trailing_newline = True
            while chunk := fh.read(_CHUNK):
                out.write(chunk)
                trailing_newline = chunk.endswith("\n")
        if not trailing_newline:
            out.write("\n")
        out.write(f"<!-- end {entry.path} -->\n")


def render_census(result: CensusResult) -> str:
    """Extension table, heaviest first."""
    out = [render_provenance(result.provenance, "census")]
    out.append("\n| extension | language | files | size | lines | ~tokens |")
    out.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for stat in result.extensions:
        out.append(
            f"| {stat.extension} | {stat.language} | {stat.files} "
            f"| {human_size(stat.size_bytes)} | {stat.line_count:,} "
            f"| {stat.token_estimate:,} |"
        )
    out.append(
        f"\n{result.total_files} files, {human_size(result.total_bytes)}, "
        f"{result.total_lines:,} lines, ~{result.token_estimate:,} tokens (chars/4)"
    )
    return "\n".join(out) + "\n"


def render_unfinished(result: UnfinishedResult) -> str:
    """Marker report grouped by file."""
    out = [render_provenance(result.provenance, "unfinished")]
    current = None
    for marker in result.markers:
        if marker.path != current:
            current = marker.path
            out.append(f"\n## {marker.path}\n")
        age = f"{marker.age_days}d old" if marker.age_days is not None else None
        notes = [n for n in (marker.author, age) if n]
        suffix = f"  ({', '.join(notes)})" if notes else ""
        out.append(f"- line {marker.line} **{marker.marker}**: {marker.text}{suffix}")
    if result.counts:
        tally = ", ".join(f"{name}: {count}" for name, count in sorted(result.counts.items()))
        out.append(f"\n{sum(result.counts.values())} markers ({tally})")
    else:
        out.append("\nnothing unfinished. suspicious.")
    return "\n".join(out) + "\n"


def _short(sha: str) -> str:
    return sha[:7]


def render_chronicle(result: ChronicleResult) -> str:
    """A commit table, or a tag-grouped changelog when one was built."""
    out = [render_provenance(result.provenance, "chronicle")]
    if result.changelog:
        for section in result.changelog:
            heading = section.tag if section.date is None else f"{section.tag} ({section.date})"
            out.append(f"\n## {heading}\n")
            for commit in section.commits:
                out.append(
                    f"- `{_short(commit.sha)}` {_cell(commit.message)} "
                    f"(+{commit.insertions}/-{commit.deletions}, {_cell(commit.author)})"
                )
    else:
        out.append("\n| sha | date | author | message | files | +ins | -del |")
        out.append("| --- | --- | --- | --- | ---: | ---: | ---: |")
        for commit in result.commits:
            out.append(
                f"| `{_short(commit.sha)}` | {commit.date} | {_cell(commit.author)} "
                f"| {_cell(commit.message)} | {commit.files_changed} "
                f"| {commit.insertions} | {commit.deletions} |"
            )
        out.append(f"\n{len(result.commits)} commits")
    return "\n".join(out) + "\n"


def _heatmap_block(grid: list[list[int]]) -> list[str]:
    """A 7x24 activity grid rendered as a fenced ASCII table."""
    peak = max((max(row) for row in grid), default=0)
    header = "     " + " ".join(f"{h:02d}" for h in range(24))
    lines = ["```", header]
    for weekday in range(7):
        cells = " ".join(_spark(grid[weekday][h], peak) for h in range(24))
        lines.append(f"{_WEEKDAYS[weekday]}  {cells}")
    lines.append("```")
    return lines


_SPARKS = " .:-=+*#%@"


def _spark(count: int, peak: int) -> str:
    if count == 0 or peak == 0:
        return " ."
    level = min(len(_SPARKS) - 1, 1 + (count * (len(_SPARKS) - 2)) // peak)
    return f" {_SPARKS[level]}"


def render_souls(result: SoulsResult) -> str:
    """Contributor table, bus factor, and (optionally) the activity heatmap."""
    out = [render_provenance(result.provenance, "souls")]
    out.append("\n| soul | commits | +ins | -del | first seen | last seen |")
    out.append("| --- | ---: | ---: | ---: | --- | --- |")
    for soul in result.souls:
        out.append(
            f"| {_cell(soul.name)} | {soul.commits} | {soul.insertions} | {soul.deletions} "
            f"| {soul.first_seen} | {soul.last_seen} |"
        )
    out.append(
        f"\n{len(result.souls)} souls, {result.total_commits} commits, "
        f"bus factor {result.bus_factor}"
    )
    if result.witching_hour:
        out.append(f"witching hour: {result.witching_hour}")
    if result.heatmap is not None:
        out.append("\n### activity (by recorded local time)\n")
        out.extend(_heatmap_block(result.heatmap))
    return "\n".join(out) + "\n"


def render_haunt(result: HauntResult) -> str:
    """Hotspot table, most-changed first."""
    out = [render_provenance(result.provenance, "haunt")]
    out.append("\n| file | commits | churn | +ins | -del |")
    out.append("| --- | ---: | ---: | ---: | ---: |")
    for spot in result.hotspots:
        out.append(
            f"| {_cell(spot.path)} | {spot.commits} | {spot.churn} "
            f"| {spot.insertions} | {spot.deletions} |"
        )
    out.append(f"\n{len(result.hotspots)} hotspots")
    return "\n".join(out) + "\n"


def render_autopsy(result: AutopsyResult) -> str:
    """A single-file dossier: vitals, authors, blame age, then its commits."""
    out = [render_provenance(result.provenance, "autopsy")]
    out.append(f"\n## {result.path}\n")
    status = "in the working tree" if result.exists else "dead (removed from the tree)"
    out.append(f"- status: {status}")
    out.append(f"- born: {result.created} (`{_short(result.created_sha)}`)")
    out.append(f"- commits: {result.commits}  (+{result.insertions}/-{result.deletions})")
    if result.former_names:
        out.append(f"- former names: {', '.join(result.former_names)}")
    if result.blame_lines is not None:
        out.append(
            f"- blame: {result.blame_lines} lines, oldest {result.oldest_line}, "
            f"newest {result.newest_line}, median age {result.median_age_days}d"
        )
    out.append("\n### authors\n")
    for share in result.authors:
        out.append(f"- {_cell(share.author)}: {share.commits} commits")
    out.append("\n### history\n")
    for commit in result.history:
        out.append(
            f"- `{_short(commit.sha)}` {commit.date} {_cell(commit.message)} "
            f"(+{commit.insertions}/-{commit.deletions})"
        )
    return "\n".join(out) + "\n"


def render_graveyard(result: GraveyardResult) -> str:
    """The dead: path, date of death, fatal commit, and its author."""
    out = [render_provenance(result.provenance, "graveyard")]
    out.append("\n| dead file | died | fatal commit | author |")
    out.append("| --- | --- | --- | --- |")
    for dead in result.dead:
        out.append(
            f"| {_cell(dead.path)} | {dead.died} | `{_short(dead.last_sha)}` "
            f"| {_cell(dead.author)} |"
        )
    out.append(f"\n{len(result.dead)} dead")
    return "\n".join(out) + "\n"


def render_ghosts(result: GhostsResult) -> str:
    """Branch hygiene table, most-abandoned first."""
    out = [render_provenance(result.provenance, "ghosts")]
    if result.threshold_days is not None:
        out.append(f"\nhaunting threshold: {result.threshold_days}d")
    out.append("\n| branch | last commit | age | author | flags |")
    out.append("| --- | --- | ---: | --- | --- |")
    for branch in result.branches:
        flags = ", ".join(
            f
            for f, on in (
                ("merged", branch.merged),
                ("gone", branch.gone_upstream),
                ("stale", branch.stale),
            )
            if on
        )
        out.append(
            f"| {_cell(branch.name)} | {branch.last_commit} | {branch.age_days}d "
            f"| {_cell(branch.author)} | {flags} |"
        )
    out.append(f"\n{len(result.branches)} branches")
    return "\n".join(out) + "\n"


def render_rot(result: RotResult) -> str:
    """Staleness table, most-neglected first."""
    out = [render_provenance(result.provenance, "rot")]
    out.append("\n| file | last touched | age | last commit |")
    out.append("| --- | --- | ---: | --- |")
    for stale in result.files:
        out.append(
            f"| {_cell(stale.path)} | {stale.last_commit} | {stale.age_days}d "
            f"| `{_short(stale.last_sha)}` |"
        )
    out.append(f"\n{len(result.files)} files")
    return "\n".join(out) + "\n"


def render_tombstone(result: TombstoneResult) -> str:
    """An ASCII tombstone stats card (art lives in art.py)."""
    from git_reaper import art

    years = f"{result.born[:4]} - {result.last[:4]}"
    lines = [
        _cell(result.name),
        years,
        "",
        f"{result.commits:,} commits",
        f"{result.souls} souls",
    ]
    if result.witching_hour:
        lines.append(f"haunted {result.witching_hour}")
    lines.append(f'"{_epitaph(result.last_words)}"')
    out = [render_provenance(result.provenance, "tombstone"), "", art.tombstone(lines)]
    return "\n".join(out) + "\n"


def _epitaph(message: str, width: int = 34) -> str:
    """Last words, trimmed (ASCII-only) so the tombstone stays a tombstone."""
    words = _cell(message)
    return words if len(words) <= width else words[: width - 3].rstrip() + "..."


def render_exhume(result: ExhumeResult) -> str:
    """Findings table, most severe first. Previews are masked, always."""
    out = [render_provenance(result.provenance, "exhume")]
    if result.findings:
        out.append("\n| severity | rule | where | preview | commit | author |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for f in result.findings:
            commit = f"`{_short(f.sha)}`" if f.sha else ""
            out.append(
                f"| {f.severity} | {f.rule} | {_cell(f.path)}:{f.line} "
                f"| `{_cell(f.preview)}` (masked) | {commit} | {_cell(f.author)} |"
            )
    tallies = {"high": 0, "medium": 0, "low": 0}
    for f in result.findings:
        tallies[f.severity] = tallies.get(f.severity, 0) + 1
    tally = ", ".join(f"{k}: {v}" for k, v in tallies.items() if v)
    out.append(
        f"\n{len(result.findings)} findings ({tally or 'none'}), "
        f"{result.blobs_scanned} blobs scanned, {result.suppressed} baselined"
    )
    if not result.findings:
        out.append("the dead kept their secrets.")
    return "\n".join(out) + "\n"


def render_veil(result: VeilResult) -> str:
    """The veiling receipt. The artifact itself goes to --out, not here."""
    out = [render_provenance(result.provenance, "veil")]
    out.append(f"\nveiled: {result.input}\n")
    if result.replacements:
        out.append("| rule | replacements |")
        out.append("| --- | ---: |")
        for count in result.replacements:
            out.append(f"| {count.rule} | {count.count} |")
    out.append(f"\n{result.total} replacements")
    return "\n".join(out) + "\n"


def render_omens(result: OmensResult) -> str:
    """The prophecy table, most cursed first. Hints, not fate."""
    out = [render_provenance(result.provenance, "omens")]
    weights = " ".join(f"{k}={v:g}" for k, v in result.weights.items())
    out.append(f"\nlens: {result.lens}   weights: {weights}\n")
    out.append("| omen | file | churn | bugs | age | size | commits |")
    out.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: |")
    for omen in result.omens:
        out.append(
            f"| {omen.score:.3f} | {_cell(omen.path)} | {omen.churn_score:.2f} "
            f"| {omen.bug_score:.2f} | {omen.age_score:.2f} | {omen.size_score:.2f} "
            f"| {omen.commits} |"
        )
    out.append(f"\n{len(result.omens)} files read. omens are hints, not fate.")
    return "\n".join(out) + "\n"


def render_doppelgangers(result: DoppelgangersResult) -> str:
    """Clusters of identical files, biggest waste first."""
    out = [render_provenance(result.provenance, "doppelgangers")]
    for cluster in result.clusters:
        out.append(
            f"\n## {human_size(cluster.size_bytes)} x {len(cluster.paths)} "
            f"(reclaimable {human_size(cluster.reclaimable_bytes)})\n"
        )
        out.extend(f"- {path}" for path in cluster.paths)
    out.append(
        f"\n{len(result.clusters)} clusters in {result.files_scanned} files, "
        f"{human_size(result.reclaimable_bytes)} reclaimable"
    )
    if not result.clusters:
        out.append("every soul here is one of a kind.")
    return "\n".join(out) + "\n"


def render_bloat(result: BloatResult) -> str:
    """Heaviest working-tree files, then the bodies still in the walls."""
    out = [render_provenance(result.provenance, "bloat")]
    out.append("\n## the living\n")
    out.append("| file | size |")
    out.append("| --- | ---: |")
    for entry in result.tree:
        out.append(f"| {_cell(entry.path)} | {human_size(entry.size_bytes)} |")
    out.append(f"\nworking tree total: {human_size(result.tree_bytes)}")
    if result.walls:
        out.append("\n## the walls (blobs gone from the tree, not from .git)\n")
        out.append("| last known as | size | blob |")
        out.append("| --- | ---: | --- |")
        for entry in result.walls:
            out.append(
                f"| {_cell(entry.path)} | {human_size(entry.size_bytes)} | `{_short(entry.sha)}` |"
            )
        out.append(f"\nstill in the walls: {human_size(result.walls_bytes)}")
    return "\n".join(out) + "\n"


def render_bones(result: BonesResult) -> str:
    """The code map: stubs per file, implementation stripped."""
    out = [render_provenance(result.provenance, "bones")]
    for file in result.files:
        out.append(f"\n## {file.path}\n")
        if not file.parsed:
            out.append(f"*skipped: {file.error}*")
            continue
        lines = ["```" + (file.language if file.language != "tsx" else "tsx")]
        for entry in file.entries:
            pad = "    " * entry.depth
            lines.append(f"{pad}{entry.signature}")
            if entry.doc:
                lines.append(f'{pad}    """{entry.doc}"""')
        lines.append("```")
        out.append("\n".join(lines))
    out.append(
        f"\n{result.parsed_files} files mapped"
        + (f", {result.skipped_files} skipped" if result.skipped_files else "")
    )
    return "\n".join(out) + "\n"


def render_scry(result: ScryResult) -> str:
    """The vision between two refs."""
    out = [render_provenance(result.provenance, "scry")]
    out.append(f"\n## {result.ref_a} .. {result.ref_b}\n")
    out.append(
        f"- {result.commits} commits, +{result.insertions}/-{result.deletions}"
    )
    if result.souls:
        hands = ", ".join(f"{_cell(s.author)} ({s.commits})" for s in result.souls)
        out.append(f"- hands: {hands}")
    if result.new_souls:
        out.append(f"- new souls: {', '.join(_cell(s) for s in result.new_souls)}")
    out.append("\n| file | commits | +ins | -del |")
    out.append("| --- | ---: | ---: | ---: |")
    for delta in result.files:
        out.append(
            f"| {_cell(delta.path)} | {delta.commits} | {delta.insertions} | {delta.deletions} |"
        )
    out.append(f"\n{len(result.files)} files changed")
    return "\n".join(out) + "\n"


def render_plague(result: PlagueResult) -> str:
    """Dependencies and their known afflictions."""
    out = [render_provenance(result.provenance, "plague")]
    if result.afflictions:
        out.append("\n## afflictions\n")
        out.append("| id | package | version | ecosystem | summary |")
        out.append("| --- | --- | --- | --- | --- |")
        for a in result.afflictions:
            out.append(
                f"| {a.id} | {_cell(a.package)} | {a.version} | {a.ecosystem} "
                f"| {_cell(a.summary)} |"
            )
    out.append("\n## dependencies\n")
    out.append("| package | version | ecosystem | manifest | pinned |")
    out.append("| --- | --- | --- | --- | --- |")
    for dep in result.dependencies:
        out.append(
            f"| {_cell(dep.name)} | {dep.version or '(range)'} | {dep.ecosystem} "
            f"| {dep.manifest} | {'yes' if dep.pinned else 'no'} |"
        )
    status = (
        f"{len(result.afflictions)} afflictions across {len(result.dependencies)} dependencies"
        if result.checked
        else "offline: manifests parsed, the oracle was not consulted"
    )
    if result.unpinned:
        status += f" ({result.unpinned} unpinned, not queried)"
    out.append(f"\n{status}")
    return "\n".join(out) + "\n"


def render_tree(result: TreeResult, with_sizes: bool = False, with_lines: bool = False) -> str:
    """ASCII tree, fenced for markdown. Deterministic: sorted, no clocks."""
    lines = [result.root.name or "."]

    def _annotate(node: TreeNode) -> str:
        notes = []
        if with_sizes and not node.is_dir:
            notes.append(human_size(node.size_bytes))
        if with_lines and not node.is_dir:
            notes.append(f"{node.line_count} lines")
        suffix = f"  ({', '.join(notes)})" if notes else ""
        return f"{node.name}{'/' if node.is_dir else ''}{suffix}"

    def _walk(node: TreeNode, prefix: str) -> None:
        for i, child in enumerate(node.children):
            last = i == len(node.children) - 1
            lines.append(f"{prefix}{'`-- ' if last else '|-- '}{_annotate(child)}")
            if child.is_dir:
                _walk(child, prefix + ("    " if last else "|   "))

    _walk(result.root, "")
    summary = f"\n{result.dir_count} directories, {result.file_count} files"
    if with_sizes:
        summary += f", {human_size(result.total_bytes)}"
    return "```\n" + "\n".join(lines) + "\n```" + summary + "\n"
