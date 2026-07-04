"""Shared git-output parsing and command shapes.

Both the subprocess and GitPython backends run the *same* git commands and
parse them the *same* way -- they differ only in how they spawn git. Keeping
the arg lists and parsers here guarantees byte-identical results across
backends (the parity tests lean on this).

Commit records use control-char separators (RS between commits, US between
fields) so a multiline body can never break the parse. `-c core.quotepath=false`
keeps non-ASCII paths as UTF-8 literals instead of git's C-quoted octal.
"""

from __future__ import annotations

import re

from git_reaper.gitio.backend import (
    BlobRecord,
    BranchRecord,
    DeadFileRecord,
    FileChange,
    FileEventRecord,
    GitCommit,
    TagRecord,
)

RS = "\x1e"
US = "\x1f"
_QUOTEPATH = ["-c", "core.quotepath=false"]
_LOG_FORMAT = f"{RS}%H{US}%an{US}%ae{US}%at{US}%aI{US}%s{US}%b{US}"
_DELETED_FORMAT = f"{RS}%H{US}%aI{US}%an"
_BRANCH_FORMAT = US.join(
    [
        "%(refname:short)",
        "%(committerdate:unix)",
        "%(committerdate:iso-strict)",
        "%(authorname)",
        "%(upstream:track)",
    ]
)
_TAG_FORMAT = US.join(
    ["%(refname:short)", "%(objectname)", "%(*objectname)", "%(creatordate:iso-strict)"]
)
_NUMSTAT = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")


# -- command arg shapes (identical across backends) ------------------------


def log_args(ref: str | None, max_count: int | None) -> list[str]:
    args = [*_QUOTEPATH, "log", f"--pretty=format:{_LOG_FORMAT}", "--numstat", "--no-renames"]
    if max_count is not None:
        args.append(f"--max-count={max_count}")
    if ref:
        args.append(ref)
    return args


def file_log_args(rel_path: str, follow: bool) -> list[str]:
    args = [*_QUOTEPATH, "log", f"--pretty=format:{_LOG_FORMAT}", "--numstat"]
    if follow:
        args.append("--follow")
    args += ["--", rel_path]
    return args


def rename_args(rel_path: str) -> list[str]:
    return [*_QUOTEPATH, "log", "--follow", "--name-status", "--format=", "--", rel_path]


def deleted_args() -> list[str]:
    # --no-renames so a rename reads as a death of the old path (matching log()).
    return [
        *_QUOTEPATH,
        "log",
        "--diff-filter=D",
        "--name-only",
        "--no-renames",
        f"--pretty=format:{_DELETED_FORMAT}",
    ]


def pickaxe_args(needle: str, regex: bool, rel_path: str | None) -> list[str]:
    """Commits whose diffs add or remove the needle (git's pickaxe)."""
    flag = f"-G{needle}" if regex else f"-S{needle}"
    args = [*_QUOTEPATH, "log", f"--pretty=format:{_LOG_FORMAT}", "--numstat", flag]
    if rel_path:
        args += ["--", rel_path]
    return args


def events_args() -> list[str]:
    # --no-renames so a rename reads as a death plus a birth (matching log()).
    return [
        *_QUOTEPATH,
        "log",
        "--name-status",
        "--no-renames",
        f"--pretty=format:{_DELETED_FORMAT}",
    ]


def branch_ref_args() -> list[str]:
    return [*_QUOTEPATH, "for-each-ref", f"--format={_BRANCH_FORMAT}", "refs/heads"]


def tag_ref_args() -> list[str]:
    return [*_QUOTEPATH, "for-each-ref", f"--format={_TAG_FORMAT}", "refs/tags"]


def object_list_args(ref: str | None = None) -> list[str]:
    """Every object reachable from `ref` (a rev, or an `A..B` range), blobs
    and trees carrying a path. `None` walks every ref (`--all`)."""
    return [*_QUOTEPATH, "rev-list", ref or "--all", "--objects"]


def batch_check_args() -> list[str]:
    """Type and uncompressed size of every object in the local store."""
    fmt = "--batch-check=%(objectname) %(objecttype) %(objectsize)"
    return ["cat-file", "--batch-all-objects", fmt]


def blob_commit_args(sha: str, path: str) -> list[str]:
    fmt = f"--pretty=format:%H{US}%aI{US}%an"
    args = [*_QUOTEPATH, "log", "--all", f"--find-object={sha}", fmt]
    if path:
        args += ["--", path]
    return args


# -- parsers ---------------------------------------------------------------


def parse_numstat(blob: str) -> list[FileChange]:
    files = []
    for line in blob.split("\n"):
        m = _NUMSTAT.match(line)
        if not m:
            continue
        ins = None if m.group(1) == "-" else int(m.group(1))
        dels = None if m.group(2) == "-" else int(m.group(2))
        files.append(FileChange(path=m.group(3), insertions=ins, deletions=dels))
    return files


def parse_log(out: str) -> list[GitCommit]:
    commits: list[GitCommit] = []
    for record in out.split(RS):
        if US not in record:
            continue  # the empty chunk before the first RS
        parts = record.split(US)
        if len(parts) < 8:
            continue
        sha, an, ae, at, aiso, subject, body = parts[:7]
        commits.append(
            GitCommit(
                sha=sha,
                author_name=an,
                author_email=ae,
                author_time=int(at),
                author_date=aiso,
                subject=subject,
                body=body.strip("\n"),
                files=parse_numstat(parts[7]),
            )
        )
    return commits


def parse_blame(out: str) -> list[tuple[str, int]]:
    lines: list[tuple[str, int]] = []
    author, when = "", 0
    for raw in out.split("\n"):
        if raw.startswith("author "):
            author = raw[7:]
        elif raw.startswith("author-time "):
            when = int(raw[12:])
        elif raw.startswith("\t"):
            lines.append((author, when))
    return lines


def parse_deleted(out: str) -> list[DeadFileRecord]:
    dead: list[DeadFileRecord] = []
    seen: set[str] = set()
    for record in out.split(RS):
        if US not in record:
            continue
        header, _, body = record.partition("\n")
        sha, date, author = header.split(US)
        for path in body.split("\n"):
            path = path.strip()
            if path and path not in seen:
                seen.add(path)
                dead.append(DeadFileRecord(path=path, sha=sha, date=date, author=author))
    return dead


def parse_events(out: str) -> list[FileEventRecord]:
    """Every add/modify/delete a commit ever recorded, newest first."""
    events: list[FileEventRecord] = []
    for record in out.split(RS):
        if US not in record:
            continue
        header, _, body = record.partition("\n")
        sha, date, _author = header.split(US)
        for line in body.split("\n"):
            status, _, path = line.partition("\t")
            if status and path:
                events.append(FileEventRecord(path=path, status=status[:1], sha=sha, date=date))
    return events


def parse_renames(out: str, rel_path: str) -> list[str]:
    seen: list[str] = []
    for line in out.split("\n"):
        if line.startswith("R"):  # Rnnn\told\tnew
            cols = line.split("\t")
            if len(cols) >= 3 and cols[1] not in seen and cols[1] != rel_path:
                seen.append(cols[1])
    return seen


def parse_branches(out: str, merged: set[str]) -> list[BranchRecord]:
    branches: list[BranchRecord] = []
    for line in out.split("\n"):
        if US not in line:
            continue
        name, when, iso, author, track = line.split(US)
        branches.append(
            BranchRecord(
                name=name,
                last_time=int(when),
                last_date=iso,
                author=author,
                merged=name in merged,
                gone_upstream="gone" in track,
            )
        )
    return branches


def parse_merged(out: str) -> set[str]:
    return {line.lstrip("* ").strip() for line in out.split("\n") if line.strip()}


def parse_blobs(object_list_out: str, batch_check_out: str) -> list[BlobRecord]:
    """Join rev-list's (sha, path) pairs with cat-file's (sha, type, size).

    rev-list names every reachable object (trees included); cat-file supplies
    the type filter and the size. Only reachable blobs survive the join.
    """
    paths: dict[str, str] = {}
    for line in object_list_out.split("\n"):
        if not line:
            continue
        sha, _, path = line.partition(" ")
        if sha not in paths:
            paths[sha] = path
    blobs: list[BlobRecord] = []
    for line in batch_check_out.split("\n"):
        parts = line.split(" ")
        if len(parts) != 3 or parts[1] != "blob":
            continue
        sha, _, size = parts
        if sha in paths:
            blobs.append(BlobRecord(sha=sha, path=paths[sha], size_bytes=int(size)))
    blobs.sort(key=lambda b: b.sha)
    return blobs


def parse_blob_commit(out: str) -> tuple[str, str, str] | None:
    """The oldest (sha, iso date, author) line from a --find-object log."""
    lines = [line for line in out.split("\n") if US in line]
    if not lines:
        return None
    sha, date, author = lines[-1].split(US)
    return sha, date, author


def parse_tags(out: str) -> list[TagRecord]:
    tags: list[TagRecord] = []
    for line in out.split("\n"):
        if US not in line:
            continue
        name, obj, deref, date = line.split(US)
        tags.append(TagRecord(name=name, sha=deref or obj, date=date))
    return tags
