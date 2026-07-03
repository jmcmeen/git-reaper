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
    DistillResult,
    DoppelgangersResult,
    EmbalmResult,
    ExhumeResult,
    ExorciseResult,
    GhostsResult,
    GraveyardResult,
    HarvestResult,
    HauntResult,
    LeechResult,
    LineageResult,
    OmensResult,
    PlagueResult,
    PossessionResult,
    ProphecyResult,
    Provenance,
    RevenantResult,
    RotResult,
    ScryResult,
    SoulsResult,
    TombstoneResult,
    TreeNode,
    TreeResult,
    UnfinishedResult,
    VeilResult,
    WakeResult,
    WardResult,
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
    out.append(f"- {result.commits} commits, +{result.insertions}/-{result.deletions}")
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


def render_ward(result: WardResult) -> str:
    """The gate report: every ward, and whether it held."""
    out = [render_provenance(result.provenance, "ward")]
    out.append(f"\npolicy from: {result.policy_source}\n")
    out.append("| ward | threshold | held | detail |")
    out.append("| --- | --- | --- | --- |")
    for check in result.checks:
        held = "yes" if check.ok else "**BROKEN**"
        out.append(f"| {check.name} | {_cell(check.threshold)} | {held} | {_cell(check.detail)} |")
    broken = sum(1 for c in result.checks if not c.ok)
    out.append(
        f"\n{len(result.checks)} wards, {broken} broken."
        + (" the circle holds." if not broken else " the circle is broken.")
    )
    return "\n".join(out) + "\n"


def render_leech(result: LeechResult) -> str:
    """What the leech drained, block by block."""
    out = [render_provenance(result.provenance, "leech")]
    out.append(f"\nleeched: {result.input} -> {result.out}\n")
    out.append("| file | language | from line | size | named by doc |")
    out.append("| --- | --- | ---: | ---: | --- |")
    for block in result.blocks:
        out.append(
            f"| {_cell(block.path)} | {block.language or '(none)'} | {block.line} "
            f"| {human_size(block.size_bytes)} | {'yes' if block.named else 'no'} |"
        )
    out.append(
        f"\n{len(result.blocks)} blocks drained"
        + (f", {result.skipped} skipped by the language filter" if result.skipped else "")
    )
    if not result.blocks:
        out.append("no fenced blood to drink here.")
    return "\n".join(out) + "\n"


def render_embalm(result: EmbalmResult) -> str:
    """The embalming receipt; the body itself is the tarball at --out."""
    out = [render_provenance(result.provenance, "embalm")]
    out.append(f"\n- preserved: {result.out}")
    out.append(f"- bodies: {result.files} files, {human_size(result.total_bytes)}")
    out.append(f"- archive sha256: `{result.archive_sha256}`")
    out.append(
        "\nthe archive carries PROVENANCE and MANIFEST.sha256 at its root; "
        "cite the sha256 above and the snapshot stays citable alone."
    )
    return "\n".join(out) + "\n"


def render_wake(result: WakeResult) -> str:
    """A Keep-a-Changelog draft: edit it, do not worship it."""
    out = [render_provenance(result.provenance, "wake")]
    since = f"since {result.since} ({result.since_date[:10]})" if result.since else "whole history"
    out.append(f"\n{result.commits} commits {since}; suggested bump: {result.suggested_bump}\n")
    out.append("## [Unreleased]")
    for section in result.sections:
        out.append(f"\n### {section.title}\n")
        for entry in section.entries:
            out.append(f"- {_cell(entry.message)} (`{_short(entry.sha)}`)")
    if not result.sections:
        out.append("\nnothing to recount; the wake is quiet.")
    out.append("\n*a draft from `reaper wake`; the reaper recounts, a human edits.*")
    return "\n".join(out) + "\n"


def render_lineage(result: LineageResult) -> str:
    """The needle's history, origin first in the telling."""
    out = [render_provenance(result.provenance, "lineage")]
    kind = "pattern" if result.regex else "string"
    where = f" under {result.path}" if result.path else ""
    out.append(f"\n## {kind}: `{_cell(result.needle)}`{where}\n")
    if result.origin is not None:
        out.append(
            f"first summoned by {_cell(result.origin.author)} on {result.origin.date} "
            f"in `{_short(result.origin.sha)}`: {_cell(result.origin.message)}"
        )
        out.append("\n| sha | date | author | message |")
        out.append("| --- | --- | --- | --- |")
        for commit in result.commits:
            out.append(
                f"| `{_short(commit.sha)}` | {commit.date} | {_cell(commit.author)} "
                f"| {_cell(commit.message)} |"
            )
        out.append(f"\n{len(result.commits)} commits touched it")
    else:
        out.append("no commit ever summoned it. the crypt does not know this line.")
    return "\n".join(out) + "\n"


def render_possession(result: PossessionResult) -> str:
    """Who holds what, and where one soul holds everything."""
    out = [render_provenance(result.provenance, "possession")]
    out.append(f"\npossession threshold: {result.threshold:g}\n")
    if result.dirs:
        out.append("## territories\n")
        out.append("| directory | dominant soul | share | commits | files |")
        out.append("| --- | --- | ---: | ---: | ---: |")
        for d in result.dirs:
            out.append(
                f"| {_cell(d.path)} | {_cell(d.owner)} | {d.share:.0%} | {d.commits} | {d.files} |"
            )
        out.append("")
    out.append("## files\n")
    out.append("| file | dominant soul | share | commits | possessed |")
    out.append("| --- | --- | ---: | ---: | --- |")
    for f in result.files:
        out.append(
            f"| {_cell(f.path)} | {_cell(f.owner)} | {f.share:.0%} "
            f"| {f.commits} | {'yes' if f.possessed else ''} |"
        )
    out.append(
        f"\n{result.possessed_count} files possessed (one soul holds >= "
        f"{result.threshold:.0%} of the commits). knowledge, not blame."
    )
    return "\n".join(out) + "\n"


def render_revenant(result: RevenantResult) -> str:
    """What would not stay buried."""
    out = [render_provenance(result.provenance, "revenant")]
    out.append("\n## risen from the grave\n")
    if result.revenants:
        out.append("| file | deaths | rebirths | last died | last raised | now |")
        out.append("| --- | ---: | ---: | --- | --- | --- |")
        for r in result.revenants:
            out.append(
                f"| {_cell(r.path)} | {r.deaths} | {r.rebirths} | {r.last_died[:10]} "
                f"| {r.last_raised[:10]} | {'alive' if r.alive else 'dead again'} |"
            )
    else:
        out.append("nothing has clawed its way back. the graves hold.")
    out.append(f"\n## repeat offenders ({result.min_fixes}+ fixes)\n")
    if result.offenders:
        out.append("| file | fixes | commits | last fix |")
        out.append("| --- | ---: | ---: | --- |")
        for o in result.offenders:
            out.append(f"| {_cell(o.path)} | {o.bug_commits} | {o.commits} | {o.last_fix[:10]} |")
    else:
        out.append("no file keeps getting 'fixed'. suspiciously well-behaved.")
    return "\n".join(out) + "\n"


def render_prophecy(result: ProphecyResult) -> str:
    """The forecast table. Like omens: hints, not fate."""
    out = [render_provenance(result.provenance, "prophecy")]
    out.append(f"\nhorizon: {result.horizon_days} days\n")
    out.append("| prophecy | file | heat | momentum | fixes | recent | prior |")
    out.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: |")
    for p in result.prophecies:
        out.append(
            f"| {p.score:.3f} | {_cell(p.path)} | {p.heat:.2f} | {p.momentum:.2f} "
            f"| {p.bug_momentum:.2f} | {p.recent_commits} | {p.prior_commits} |"
        )
    out.append(
        f"\n{len(result.prophecies)} files read. prophecies are hints, not fate; "
        "the future belongs to whoever writes the next commit."
    )
    return "\n".join(out) + "\n"


def render_exorcise(result: ExorciseResult) -> str:
    """The purge plan. Printed, never performed."""
    out = [render_provenance(result.provenance, "exorcise")]
    if not result.targets:
        out.append("\nnothing worth expelling. the walls are clean.")
        return "\n".join(out) + "\n"
    out.append("\n## what to expel\n")
    out.append("| path | reason | size | sha |")
    out.append("| --- | --- | ---: | --- |")
    for target in result.targets:
        size = human_size(target.size_bytes) if target.size_bytes else ""
        sha = f"`{_short(target.sha)}`" if target.sha else ""
        out.append(f"| {_cell(target.path)} | {_cell(target.reason)} | {size} | {sha} |")
    out.append("\n## the rite (run none of this lightly)\n")
    out.append("```sh")
    out.extend(result.commands)
    out.append("```")
    out.append("\n## warnings\n")
    for warning in result.warnings:
        out.append(f"- {warning}")
    out.append("\nthe reaper plans; only you may swing. nothing above was executed.")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# distill: the Agent Skill bundle
# --------------------------------------------------------------------------


def _skill_stamp(result: DistillResult) -> str:
    """The provenance block a skill carries; `distill --check` reads it back."""
    extra = [
        f"sha:       {result.provenance.sha or 'unknown'}",
        f"profile:   {result.profile}",
    ]
    return render_provenance(result.provenance, "distill", extra=extra)


def render_skill_bundle(result: DistillResult) -> dict[str, str]:
    """Every file in the skill directory, path -> content."""
    files = {
        "SKILL.md": render_skill(result),
        "reference/conventions.md": render_skill_conventions(result),
        "reference/commands.md": render_skill_commands(result),
        "reference/gotchas.md": render_skill_gotchas(result),
        "reference/ownership.md": render_skill_ownership(result),
    }
    if result.bones is not None:
        files["reference/structure.md"] = render_bones(result.bones)
    return files


def render_skill(result: DistillResult) -> str:
    """SKILL.md: frontmatter, the distill stamp, and the route into reference/."""
    description = result.description.replace('"', '\\"')
    out = [
        "---",
        f"name: {result.name}",
        f'description: "{description}"',
        "---",
        "",
        _skill_stamp(result),
    ]
    tongues = ", ".join(dict.fromkeys(s.language for s in result.languages if s.language)) or "n/a"
    if result.profile == "onboarding":
        out.append(f"# Welcome to {result.name}")
        out.append("")
        out.append(
            f"This guide was distilled from the repository itself ({result.total_files} "
            f"files, mostly {tongues}). Everything below was measured, not remembered, "
            "so trust it over folklore -- and check the stamp above if it smells stale."
        )
    elif result.profile == "stack":
        out.append(f"# Working on the {tongues} stack (distilled from {result.name})")
        out.append("")
        out.append(
            "Use this skill when working in this repository or a sibling built on the "
            "same stack. It carries the tooling, commands, and conventions; the "
            "repo-specific maps in reference/ are examples of the house style."
        )
    else:
        out.append(f"# Working in {result.name}")
        out.append("")
        out.append(
            f"Use this skill when reading or changing code in {result.name}. It was "
            "distilled from the repository itself: real commands, measured hotspots, "
            "the actual commit style."
        )
    out.append("")
    out.append("## The essentials")
    out.append("")
    if result.layout:
        out.append(f"- Layout: {', '.join(f'`{e}`' for e in result.layout[:12])}")
    out.append(f"- Languages: {tongues} across {result.total_files} files")
    if result.tooling:
        out.append(f"- Tooling: {', '.join(f'`{t}`' for t in result.tooling)}")
    test = next((c for c in result.commands if c.kind == "test"), None)
    lint = next((c for c in result.commands if c.kind == "lint"), None)
    if test:
        out.append(f"- Test with `{test.command}` (from {test.origin})")
    if lint:
        out.append(f"- Lint with `{lint.command}` (from {lint.origin})")
    if result.conventional_share >= 0.5:
        top = ", ".join(f"`{p}:`" for p in list(result.commit_prefixes)[:4])
        out.append(
            f"- Commits follow conventional prefixes ({result.conventional_share:.0%} "
            f"of history; mostly {top})"
        )
    out.append("")
    out.append("## Read next")
    out.append("")
    refs = [
        ("reference/structure.md", "the bones map: imports, signatures, docstrings"),
        ("reference/conventions.md", "naming, layout, lint/format, commit style"),
        ("reference/commands.md", "real build/test/lint/run commands, not guesses"),
        ("reference/gotchas.md", "the files that break most, and the themes that recur"),
        ("reference/ownership.md", "who to ask"),
    ]
    for path, blurb in refs:
        out.append(f"- `{path}` -- {blurb}")
    out.append("")
    out.append(
        "Freshness: this skill is stamped with the source and sha above; "
        "`reaper distill --check <this directory>` reports it stale once the code moves on."
    )
    return "\n".join(out) + "\n"


def render_skill_conventions(result: DistillResult) -> str:
    """conventions.md: what the repo does by habit, measured from itself."""
    out = [_skill_stamp(result), "# Conventions", ""]
    if result.layout:
        out.append("## Layout")
        out.append("")
        for entry in result.layout:
            out.append(f"- `{entry}`")
        out.append("")
    if result.languages:
        out.append("## Languages")
        out.append("")
        out.append("| language | extension | files | lines |")
        out.append("| --- | --- | ---: | ---: |")
        for stat in result.languages[:10]:
            out.append(
                f"| {stat.language or '(none)'} | {stat.extension} "
                f"| {stat.files} | {stat.line_count:,} |"
            )
        out.append("")
    if result.tooling:
        out.append("## Tooling on the premises")
        out.append("")
        for tool in result.tooling:
            out.append(f"- `{tool}`")
        out.append("")
    out.append("## Commit style")
    out.append("")
    if result.commits_sampled == 0:
        out.append("No commit history to read.")
    elif result.conventional_share >= 0.25:
        out.append(
            f"Conventional-commit prefixes on {result.conventional_share:.0%} of "
            f"{result.commits_sampled} commits:"
        )
        out.append("")
        for prefix, count in result.commit_prefixes.items():
            out.append(f"- `{prefix}:` x{count}")
    else:
        out.append(
            f"Free-form subjects ({result.commits_sampled} commits sampled; only "
            f"{result.conventional_share:.0%} carry a conventional prefix)."
        )
    return "\n".join(out) + "\n"


def render_skill_commands(result: DistillResult) -> str:
    """commands.md: commands lifted from the repo's own files, grouped by kind."""
    out = [_skill_stamp(result), "# Commands", ""]
    if not result.commands:
        out.append("No build/test/lint commands were found in the usual places.")
        return "\n".join(out) + "\n"
    out.append("Lifted from the repo's own tooling files, not guessed.")
    out.append("")
    for kind in ("test", "lint", "format", "build", "run", "docs", "other"):
        hints = [c for c in result.commands if c.kind == kind]
        if not hints:
            continue
        out.append(f"## {kind}")
        out.append("")
        for hint in hints:
            out.append(f"- `{_cell(hint.command)}` (from {hint.origin})")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def render_skill_gotchas(result: DistillResult) -> str:
    """gotchas.md: the files that break most, and the recurring failure themes."""
    out = [_skill_stamp(result), "# Gotchas", ""]
    if result.gotchas:
        out.append("Files that change (and get fixed) most; tread carefully here.")
        out.append("")
        out.append("| file | commits | bug fixes | churn |")
        out.append("| --- | ---: | ---: | ---: |")
        for g in result.gotchas:
            out.append(f"| {_cell(g.path)} | {g.commits} | {g.bug_commits} | {g.churn:,} |")
        out.append("")
    if result.bug_themes:
        out.append("## Recurring fix themes")
        out.append("")
        for word, count in result.bug_themes.items():
            out.append(f"- {word} (x{count})")
        out.append("")
    if result.marker_counts:
        counted = ", ".join(f"{m} x{n}" for m, n in sorted(result.marker_counts.items()))
        out.append(f"## Known debt\n\n{counted} markers are haunting the tree.")
    if len(out) == 3:
        out.append("Nothing recurs yet; the history is too young to haunt.")
    return "\n".join(out).rstrip("\n") + "\n"


def render_skill_ownership(result: DistillResult) -> str:
    """ownership.md: who to ask, or anonymous roles under --anon."""
    out = [_skill_stamp(result), "# Ownership", ""]
    if not result.owners:
        out.append("No souls on record.")
        return "\n".join(out) + "\n"
    out.append(f"Bus factor: {result.bus_factor}")
    out.append("")
    out.append("| who | commits | +ins | -del | last seen |")
    out.append("| --- | ---: | ---: | ---: | --- |")
    for soul in result.owners:
        who = _cell(soul.name) + (f" <{_cell(soul.email)}>" if soul.email else "")
        out.append(
            f"| {who} | {soul.commits} | {soul.insertions:,} "
            f"| {soul.deletions:,} | {soul.last_seen[:10]} |"
        )
    return "\n".join(out) + "\n"
