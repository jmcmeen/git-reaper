"""Conjure: bundle a repo into a single LLM-ingestible artifact.

The packed format is a spec, not an accident (schema conjure/v1):

- Provenance block first, then the file tree, then every text file in
  deterministic sorted order.
- Each file: a ``## path`` header, an optional ``<!-- meta ... -->`` line
  (sha256, nonce, no-eol), a backtick fence computed to be longer than any
  backtick run inside the content, the raw content, the closing fence, and
  an end marker that repeats the path.
- If the content contains its own end marker, the marker gains a numeric
  nonce on both ends, recorded on the meta line.
- Files whose content does not end in a newline get one added before the
  closing fence and a ``no-eol`` meta token so reanimate can strip it.

The property that guards all of this: reanimate(conjure(tree)) == tree,
byte for byte. Binary and non-UTF-8 files are skipped with receipts.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

from git_reaper import fsutil
from git_reaper.core import rules as rules_engine
from git_reaper.core.harvest import CapExceeded
from git_reaper.core.provenance import make_provenance
from git_reaper.formatters.markdown import render_provenance
from git_reaper.ignore import IgnoreMatcher, walk_files
from git_reaper.models import FileEntry, PackedFile, PackResult, RepoRef
from git_reaper.schemas import artifact_schema

TREE_OPEN = "<!-- tree -->"
TREE_CLOSE = "<!-- end tree -->"

_BACKTICKS = re.compile(r"`+")


def end_marker(path: str, nonce: int | None) -> str:
    tag = f"end#{nonce}" if nonce is not None else "end"
    return f"<!-- {tag} {path} -->"


def _fence_for(text: str) -> int:
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    return max(3, longest + 1)


def _read_text(path: Path, veil_rules: list[rules_engine.Rule] | None = None) -> str | None:
    """Strict UTF-8, no newline translation. None if it will not decode.

    When veiling, the same redaction runs in the analyze and render passes,
    so fences, hashes, and line counts always describe the veiled content.
    """
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            text = fh.read()
    except UnicodeDecodeError:
        return None
    if veil_rules is not None:
        text = rules_engine.veil_text(text, rules=veil_rules).text
    return text


def conjure(
    repo: RepoRef,
    excludes: list[str] | None = None,
    max_file_size: int | None = None,
    max_total_size: int | None = None,
    with_sha256: bool = False,
    split_tokens: int | None = None,
    veil_rules: list[rules_engine.Rule] | None = None,
    invoked: str = "reaper conjure",
    generated: str | None = None,
) -> PackResult:
    """Analyze the tree and decide, per file, how it will be packed.

    Rendering happens in iter_parts(); this pass records everything needed
    to write the artifact (fence length, nonce, no-eol, hash) so the output
    is fully determined before a byte is emitted.
    """
    root = Path(repo.path)
    matcher = IgnoreMatcher(root, extra_excludes=excludes)
    result = PackResult(
        provenance=make_provenance(artifact_schema("conjure"), repo, invoked, generated),
        root=str(root),
        split_tokens=split_tokens,
    )

    for path in walk_files(root, matcher):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if max_file_size is not None and size > max_file_size:
            result.skipped.append(
                FileEntry(path=rel, size_bytes=size, skipped=True, skip_reason="over size cap")
            )
            continue
        if fsutil.is_binary(path):
            result.skipped.append(
                FileEntry(path=rel, size_bytes=size, skipped=True, skip_reason="binary")
            )
            continue
        content = _read_text(path)
        if content is None:
            result.skipped.append(
                FileEntry(path=rel, size_bytes=size, skipped=True, skip_reason="not valid UTF-8")
            )
            continue
        if veil_rules is not None:
            veiled = rules_engine.veil_text(content, rules=veil_rules)
            content = veiled.text
            result.veiled += veiled.total
        if max_total_size is not None and result.total_bytes + size > max_total_size:
            raise CapExceeded(
                f"total size cap ({fsutil.human_size(max_total_size)}) hit at {rel}; "
                "raise --max-total-size or add excludes"
            )

        nonce = None
        if end_marker(rel, None) in content:
            nonce = 1
            while end_marker(rel, nonce) in content:
                nonce += 1
        entry = PackedFile(
            path=rel,
            size_bytes=size,
            line_count=content.count("\n") + (0 if content.endswith("\n") or not content else 1),
            token_estimate=fsutil.estimate_tokens(len(content)),
            fence_len=_fence_for(content),
            nonce=nonce,
            no_eol=bool(content) and not content.endswith("\n"),
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest() if with_sha256 else None,
        )
        result.files.append(entry)
        result.total_bytes += size
        result.token_estimate += entry.token_estimate

    result.provenance.files = len(result.files)
    result.provenance.token_estimate = result.token_estimate
    result.parts = len(_assign_parts(result))
    return result


def _assign_parts(result: PackResult) -> list[list[PackedFile]]:
    """Greedy sharding by token estimate, preserving sorted order."""
    if not result.split_tokens:
        return [list(result.files)]
    parts: list[list[PackedFile]] = [[]]
    budget = 0
    for entry in result.files:
        if parts[-1] and budget + entry.token_estimate > result.split_tokens:
            parts.append([])
            budget = 0
        parts[-1].append(entry)
        budget += entry.token_estimate
    return parts


def _render_tree(paths: list[str]) -> str:
    """A compact nested listing of the packed files."""
    lines: list[str] = []
    seen_dirs: set[str] = set()
    for path in paths:
        parts = path.split("/")
        for depth in range(len(parts) - 1):
            prefix = "/".join(parts[: depth + 1])
            if prefix not in seen_dirs:
                seen_dirs.add(prefix)
                lines.append("  " * depth + parts[depth] + "/")
        lines.append("  " * (len(parts) - 1) + parts[-1])
    return "\n".join(lines)


def _render_file(
    entry: PackedFile, root: Path, veil_rules: list[rules_engine.Rule] | None = None
) -> str:
    content = _read_text(root / entry.path, veil_rules)
    if content is None:  # pragma: no cover - vanished/changed between passes
        raise CapExceeded(f"{entry.path} changed while packing; rerun the ritual")
    meta: list[str] = []
    if entry.sha256:
        meta.append(f"sha256:{entry.sha256}")
    if entry.nonce is not None:
        meta.append(f"nonce:{entry.nonce}")
    if entry.no_eol:
        meta.append("no-eol")
    fence = "`" * entry.fence_len
    pieces = [f"\n## {entry.path}\n"]
    if meta:
        pieces.append(f"<!-- meta {' '.join(meta)} -->\n")
    pieces.append(f"{fence}\n")
    pieces.append(content)
    if entry.no_eol:
        pieces.append("\n")
    pieces.append(f"{fence}\n{end_marker(entry.path, entry.nonce)}\n")
    return "".join(pieces)


def iter_parts(
    result: PackResult, veil_rules: list[rules_engine.Rule] | None = None
) -> Iterator[tuple[int, str]]:
    """Yield (part_number, text). Part 1 carries the tree and the receipts;
    every part repeats the provenance block (with part: i/n when sharded).
    Pass the same veil_rules given to conjure(), or the receipts will lie."""
    root = Path(result.root)
    parts = _assign_parts(result)
    total = len(parts)
    for number, entries in enumerate(parts, start=1):
        extra = [f"part:      {number}/{total}"] if total > 1 else []
        if result.veiled:
            extra.append(f"veiled:    {result.veiled} replacements")
        pieces = [render_provenance(result.provenance, "conjure", extra=extra)]
        if number == 1:
            tree_text = _render_tree([f.path for f in result.files])
            fence = "`" * _fence_for(tree_text)
            pieces.append(f"\n{TREE_OPEN}\n{fence}\n{tree_text}\n{fence}\n{TREE_CLOSE}\n")
            for skipped in result.skipped:
                pieces.append(f"<!-- skipped {skipped.path}: {skipped.skip_reason} -->\n")
        for entry in entries:
            pieces.append(_render_file(entry, root, veil_rules))
        yield number, "".join(pieces)
