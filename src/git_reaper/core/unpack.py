"""Reanimate: reconstruct a directory tree from a conjured artifact.

The parser is a strict sequential state machine over the conjure/v1 format;
it never scans inside fenced content, so file bodies can contain headers,
fences shorter than their wrapper, and fake end markers without confusing
it. Path traversal is refused outright (the zip-slip lesson).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from git_reaper.core.pack import TREE_CLOSE, TREE_OPEN, end_marker
from git_reaper.models import ReanimatedFile, ReanimateResult

_FENCE_RE = re.compile(r"^`{3,}$")
_META_RE = re.compile(r"^<!-- meta (?P<tokens>.+) -->$")
_SCHEMA_RE = re.compile(r"^schema:\s+(?P<schema>\S+)$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ReanimateError(ValueError):
    """The artifact does not parse, or refuses to be written safely."""


def _unsafe(path: str) -> str | None:
    """Reason a packed path must not be written, or None if it is safe."""
    if not path or "\x00" in path or "\\" in path:
        return "malformed path"
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return "absolute path"
    segments = path.split("/")
    if ".." in segments:
        return "path traversal ('..')"
    if "" in segments or "." in segments:
        return "malformed path"
    return None


class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = text.split("\n")
        self.pos = 0

    def _line(self) -> str | None:
        if self.pos >= len(self.lines):
            return None
        return self.lines[self.pos].rstrip("\r")

    def _fail(self, why: str) -> ReanimateError:
        return ReanimateError(f"artifact line {self.pos + 1}: {why}")

    def _skip_blank_and_receipts(self) -> None:
        while (line := self._line()) is not None:
            if line == "" or line.startswith("<!-- skipped "):
                self.pos += 1
            else:
                return

    def _skip_comment_block(self) -> str | None:
        """Consume a provenance block; return its schema line if present."""
        schema = None
        while (line := self._line()) is not None:
            self.pos += 1
            found = _SCHEMA_RE.match(line)
            if found:
                schema = found.group("schema")
            if line == "-->":
                return schema
        raise self._fail("unterminated provenance block")

    def _skip_tree(self) -> None:
        self.pos += 1  # TREE_OPEN
        line = self._line()
        if line is None or not _FENCE_RE.match(line):
            raise self._fail("expected a fence after the tree marker")
        fence = line
        self.pos += 1
        while (line := self._line()) is not None:
            self.pos += 1
            if line == fence:
                break
        else:
            raise self._fail("unterminated tree block")
        if self._line() != TREE_CLOSE:
            raise self._fail("missing end-of-tree marker")
        self.pos += 1

    def _read_meta(self) -> tuple[str | None, int | None, bool]:
        line = self._line()
        sha256, nonce, no_eol = None, None, False
        if line is None:
            return sha256, nonce, no_eol
        found = _META_RE.match(line)
        if not found:
            return sha256, nonce, no_eol
        for token in found.group("tokens").split(" "):
            if token.startswith("sha256:") and _SHA_RE.match(token[7:]):
                sha256 = token[7:]
            elif token.startswith("nonce:") and token[6:].isdigit():
                nonce = int(token[6:])
            elif token == "no-eol":
                no_eol = True
            else:
                raise self._fail(f"unknown meta token {token!r}")
        self.pos += 1
        return sha256, nonce, no_eol

    def _read_file(self) -> tuple[str, str, str | None]:
        """One file section: returns (path, content, sha256)."""
        header = self._line()
        assert header is not None and header.startswith("## ")
        path = header[3:]
        self.pos += 1
        sha256, nonce, no_eol = self._read_meta()
        fence_line = self._line()
        if fence_line is None or not _FENCE_RE.match(fence_line):
            raise self._fail(f"expected a fence after the header for {path!r}")
        fence = fence_line
        self.pos += 1
        collected: list[str] = []
        while True:
            line = self._line()
            if line is None:
                raise self._fail(f"unterminated content for {path!r}")
            self.pos += 1
            if line == fence:
                break
            collected.append(self.lines[self.pos - 1])  # raw, keep any \r
        content = "\n".join(collected) + "\n" if collected else ""
        if no_eol:
            if not content.endswith("\n"):
                raise self._fail(f"no-eol marked but no newline to strip for {path!r}")
            content = content[:-1]
        marker = self._line()
        if marker != end_marker(path, nonce):
            raise self._fail(f"missing or mismatched end marker for {path!r}")
        self.pos += 1
        return path, content, sha256

    def sections(self) -> tuple[str | None, list[tuple[str, str, str | None]]]:
        """Parse the whole artifact (or several concatenated parts)."""
        schema = None
        files: list[tuple[str, str, str | None]] = []
        while True:
            self._skip_blank_and_receipts()
            line = self._line()
            if line is None:
                return schema, files
            if line == TREE_OPEN:
                self._skip_tree()
            elif line == "<!--":
                schema = self._skip_comment_block() or schema
            elif line.startswith("## "):
                files.append(self._read_file())
            else:
                raise self._fail(f"unexpected line {line!r}")


def reanimate(
    text: str,
    out_dir: Path,
    force: bool = False,
    verify: bool = False,
) -> ReanimateResult:
    """Raise the packed tree into out_dir.

    The target must be empty (or missing) unless force is set. With verify,
    per-file sha256 meta is checked and mismatches are reported; files are
    still written so the wreckage can be examined.
    """
    schema, sections = _Parser(text).sections()
    result = ReanimateResult(out=str(out_dir), schema=schema)

    if out_dir.exists() and not force and any(out_dir.iterdir()):
        raise ReanimateError(
            f"{out_dir} is not empty; give an empty plot or use --force to overwrite"
        )

    seen: set[str] = set()
    for path, content, sha256 in sections:
        reason = _unsafe(path)
        if reason:
            raise ReanimateError(f"refusing to write {path!r}: {reason}")
        if path in seen:
            raise ReanimateError(f"duplicate file in artifact: {path!r}")
        seen.add(path)

        verified: bool | None = None
        if verify and sha256:
            verified = hashlib.sha256(content.encode("utf-8")).hexdigest() == sha256
            if not verified:
                result.verify_failures.append(path)

        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        result.files.append(
            ReanimatedFile(path=path, size_bytes=len(content.encode("utf-8")), verified=verified)
        )
    return result
