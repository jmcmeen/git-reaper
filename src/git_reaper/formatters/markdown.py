"""Markdown rendering: provenance blocks, harvest artifacts, tree listings.

Harvest artifacts are streamed: file contents are read chunk by chunk while
writing, so peak memory is bounded by a chunk, not the repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from git_reaper.fsutil import human_size
from git_reaper.models import (
    CensusResult,
    HarvestResult,
    Provenance,
    TreeNode,
    TreeResult,
    UnfinishedResult,
)

_CHUNK = 65536


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
