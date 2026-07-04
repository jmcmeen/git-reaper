"""Leech: drain fenced code blocks out of markdown back into files.

The inverse of harvest for ordinary documents (READMEs, tutorials, model
output that never went through conjure). A CommonMark-style scanner walks
the fences; blocks the document itself names (a path-looking token or a
`title=`/`filename=`/`file=`/`path=` attribute in the info string) keep
their name, the rest are numbered by language. Path safety reuses
reanimate's guards -- a document cannot leech itself outside --out.
"""

from __future__ import annotations

import re
from pathlib import Path

from git_reaper import fsutil
from git_reaper.core.provenance import make_provenance
from git_reaper.core.unpack import ReanimateError, _unsafe
from git_reaper.models import LeechBlock, LeechResult, RepoRef
from git_reaper.schemas import artifact_schema

_FENCE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})\s*(?P<info>.*)$")
_NAME_ATTR = re.compile(r"""(?:title|filename|file|path)=["']?(?P<name>[^"'\s]+)["']?""")

#: Fence info language -> file extension for unnamed blocks.
EXTENSIONS = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "tsx": "tsx",
    "jsx": "jsx",
    "bash": "sh",
    "sh": "sh",
    "shell": "sh",
    "zsh": "sh",
    "console": "sh",
    "rust": "rs",
    "rs": "rs",
    "go": "go",
    "java": "java",
    "kotlin": "kt",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "h": "h",
    "cs": "cs",
    "ruby": "rb",
    "rb": "rb",
    "php": "php",
    "swift": "swift",
    "sql": "sql",
    "html": "html",
    "css": "css",
    "json": "json",
    "yaml": "yml",
    "yml": "yml",
    "toml": "toml",
    "ini": "ini",
    "xml": "xml",
    "markdown": "md",
    "md": "md",
    "diff": "diff",
    "dockerfile": "dockerfile",
    "makefile": "mk",
}


class LeechError(ValueError):
    """The document cannot be leeched safely. Message says why."""


def _looks_like_path(token: str) -> bool:
    """A bare info token the author probably meant as a filename."""
    return ("/" in token or "." in token) and not token.startswith(("{", "."))


def _block_name(info: str) -> tuple[str, str | None]:
    """(language, explicit path or None) from a fence's info string."""
    info = info.strip()
    if not info:
        return "", None
    tokens = info.split()
    if _looks_like_path(tokens[0]):
        return "", tokens[0]
    language = tokens[0].lstrip("{.").rstrip("}").lower()
    attr = _NAME_ATTR.search(info)
    if attr:
        return language, attr.group("name")
    for token in tokens[1:]:
        if "=" not in token and _looks_like_path(token):
            return language, token
    return language, None


def leech(
    text: str,
    source_name: str,
    repo: RepoRef,
    lang: str | None = None,
    invoked: str = "reaper leech",
    generated: str | None = None,
) -> tuple[LeechResult, dict[str, str]]:
    """Pull every fenced block out of the document.

    Returns the result model and {relative path: content}; writing is the
    caller's business (the CLI points it at --out).
    """
    result = LeechResult(
        provenance=make_provenance(artifact_schema("leech"), repo, invoked, generated),
        input=source_name,
    )
    contents: dict[str, str] = {}
    stem = Path(source_name).stem if source_name != "-" else "stdin"

    lines = text.split("\n")
    i = 0
    counter = 0
    while i < len(lines):
        match = _FENCE.match(lines[i])
        if not match or (match.group("fence").startswith("`") and "`" in match.group("info")):
            i += 1
            continue
        fence, info, opened_at = match.group("fence"), match.group("info"), i + 1
        close = re.compile(rf"^ {{0,3}}{fence[0]}{{{len(fence)},}}\s*$")
        body: list[str] = []
        i += 1
        while i < len(lines) and not close.match(lines[i]):
            body.append(lines[i])
            i += 1
        if i >= len(lines):
            break  # unterminated fence: prose, not a block
        i += 1

        language, named_path = _block_name(info)
        if lang is not None and language != lang.lower():
            result.skipped += 1
            continue
        counter += 1
        if named_path is not None:
            reason = _unsafe(named_path.replace("\\", "/"))
            if reason:
                raise LeechError(f"refusing to write {named_path!r}: {reason}")
            path = named_path.replace("\\", "/")
        else:
            ext = EXTENSIONS.get(language, language or "txt")
            path = f"{stem}.block-{counter:02d}.{ext}"
        path = _dedupe(path, contents)
        content = "\n".join(body) + "\n" if body else ""
        contents[path] = content
        result.blocks.append(
            LeechBlock(
                path=path,
                language=language,
                line=opened_at,
                size_bytes=len(content.encode("utf-8")),
                named=named_path is not None,
            )
        )
    result.provenance.files = len(result.blocks)
    return result, contents


def _dedupe(path: str, contents: dict[str, str]) -> str:
    """The same name twice gets a numeric suffix, never an overwrite."""
    if path not in contents:
        return path
    stem, dot, ext = path.rpartition(".")
    for n in range(2, 1000):
        candidate = f"{stem}-{n}.{ext}" if dot else f"{path}-{n}"
        if candidate not in contents:
            return candidate
    raise LeechError(f"a thousand blocks named {path!r}; name some of them")


def write_blocks(
    contents: dict[str, str], out_dir: Path, force: bool = False, archive: str | None = None
) -> Path:
    """Write the drained blocks under out_dir (must be empty unless force).

    archive, one of fsutil.ARCHIVE_FORMATS, packages out_dir into a single
    file instead of leaving it as a loose directory. Returns the final path
    (out_dir itself, or the archive when one was requested).
    """
    if out_dir.exists() and not force and any(out_dir.iterdir()):
        raise ReanimateError(
            f"{out_dir} is not empty; give an empty plot or use --force to overwrite"
        )
    for rel, content in sorted(contents.items()):
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as fh:
            fh.write(content)
    if archive:
        archived = fsutil.make_archive(out_dir, archive)
        fsutil.force_rmtree(out_dir)
        return archived
    return out_dir
