"""Markdown rendering: provenance blocks, harvest artifacts, tree listings.

Harvest artifacts are streamed: file contents are read chunk by chunk while
writing, so peak memory is bounded by a chunk, not the repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from git_reaper.fsutil import human_size
from git_reaper.models import HarvestResult, Provenance, TreeNode, TreeResult

_CHUNK = 65536


def render_provenance(prov: Provenance, kind: str) -> str:
    """The header block every combined artifact opens with."""
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
        "-->",
    ]
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
