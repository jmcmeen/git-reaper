"""Optional libgit2 backend (the ``git-reaper[pygit2]`` extra): the
performance pass for history-heavy rituals.

Unlike GitPython (which still drives the git CLI), pygit2 binds libgit2
directly, so the bulk read paths -- the full commit log with per-file churn,
blob enumeration, blob reads, blame, tags -- run in-process with no
subprocess per call. Everything that touches the network or the working
tree (clone, fetch, checkout) and the rare per-file log shapes (--follow,
pickaxe) stay delegated to the subprocess backend, where real git behavior
is the spec. The parity tests hold this backend to byte-identical results
on the shared fixtures.

Selected with GIT_REAPER_BACKEND=pygit2; never imported otherwise, so the
base install stays free of the compiled dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from git_reaper.gitio.backend import (
    BlobRecord,
    FileChange,
    GitCommit,
    GitError,
    TagRecord,
)
from git_reaper.gitio.subprocess_git import SubprocessGit


def _import_pygit2() -> Any:
    """The `pygit2` module, or a clear error if the extra is missing."""
    try:
        import pygit2

        return pygit2
    except ImportError as exc:
        raise GitError("the pygit2 backend needs the extra; install `git-reaper[pygit2]`") from exc


def _iso(when: int, offset_minutes: int) -> str:
    """Strict ISO 8601 with the recorded offset, matching git's %aI
    (which renders a UTC offset as 'Z', not '+00:00')."""
    tz = timezone(timedelta(minutes=offset_minutes))
    stamp = datetime.fromtimestamp(when, tz=tz).isoformat()
    return stamp[:-6] + "Z" if stamp.endswith("+00:00") else stamp


def _split_message(message: str) -> tuple[str, str]:
    """git's %s / %b split: subject up to the first blank line (newlines
    folded to spaces), body after it."""
    head, _, rest = message.partition("\n\n")
    subject = " ".join(head.strip("\n").splitlines())
    return subject, rest.strip("\n")


class Pygit2Git(SubprocessGit):
    """libgit2 for the hot read paths; the subprocess backend for the rest."""

    def __init__(self) -> None:
        self._pygit2: Any = _import_pygit2()

    def _repo(self, path: Path) -> Any:
        found = self._pygit2.discover_repository(str(path))
        if found is None:
            raise GitError(f"not a git repository: {path}")
        return self._pygit2.Repository(found)

    def is_repo(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        found = self._pygit2.discover_repository(str(path))
        if found is None:
            return False
        return not self._pygit2.Repository(found).is_bare

    def head_sha(self, repo: Path) -> str | None:
        try:
            return str(self._repo(repo).head.target)
        except Exception:
            return None

    def current_branch(self, repo: Path) -> str | None:
        try:
            gitrepo = self._repo(repo)
            if gitrepo.head_is_detached or gitrepo.head_is_unborn:
                return None
            name: str = gitrepo.head.shorthand
            return name or None
        except Exception:
            return None

    # -- history mining ------------------------------------------------------

    def log(
        self, repo: Path, ref: str | None = None, max_count: int | None = None
    ) -> list[GitCommit]:
        gitrepo = self._repo(repo)
        try:
            start = gitrepo.revparse_single(ref).peel(self._pygit2.Commit) if ref else None
            if start is None:
                if gitrepo.head_is_unborn:
                    return []
                start = gitrepo[gitrepo.head.target]
        except (KeyError, self._pygit2.GitError) as exc:
            raise GitError(f"git log failed (in {repo}): unknown ref {ref!r}") from exc
        commits: list[GitCommit] = []
        for commit in gitrepo.walk(start.id, self._pygit2.GIT_SORT_NONE):
            if max_count is not None and len(commits) >= max_count:
                break
            subject, body = _split_message(commit.message)
            commits.append(
                GitCommit(
                    sha=str(commit.id),
                    author_name=commit.author.name,
                    author_email=commit.author.email,
                    author_time=commit.author.time,
                    author_date=_iso(commit.author.time, commit.author.offset),
                    subject=subject,
                    body=body,
                    files=self._numstat(gitrepo, commit),
                )
            )
        return commits

    def _numstat(self, gitrepo: Any, commit: Any) -> list[FileChange]:
        """Per-file churn matching `git log --numstat --no-renames`: merge
        commits report nothing, binaries report None/None."""
        if len(commit.parents) > 1:
            return []
        if commit.parents:
            diff = gitrepo.diff(commit.parents[0], commit)
        else:
            # Root commit: everything is an addition against the empty tree.
            diff = commit.tree.diff_to_tree(swap=True)
        files: list[FileChange] = []
        for patch in diff:
            path = patch.delta.new_file.path or patch.delta.old_file.path
            if patch.delta.is_binary:
                files.append(FileChange(path=path, insertions=None, deletions=None))
            else:
                _context, additions, deletions = patch.line_stats
                files.append(FileChange(path=path, insertions=additions, deletions=deletions))
        files.sort(key=lambda f: f.path)
        return files

    def show_file(self, repo: Path, rev: str, rel_path: str) -> bytes | None:
        gitrepo = self._repo(repo)
        try:
            tree = gitrepo.revparse_single(rev).peel(self._pygit2.Tree)
            entry = tree[rel_path]
        except (KeyError, self._pygit2.GitError):
            return None
        blob = gitrepo[entry.id]
        data: bytes = blob.data
        return data

    def cat_blob(self, repo: Path, sha: str) -> bytes | None:
        gitrepo = self._repo(repo)
        try:
            obj = gitrepo[sha]
        except (KeyError, ValueError):
            return None
        if obj.type != self._pygit2.GIT_OBJECT_BLOB:
            return None
        data: bytes = obj.data
        return data

    def tags(self, repo: Path) -> list[TagRecord]:
        """Tags with annotated ones dereferenced, sorted by refname like
        for-each-ref."""
        gitrepo = self._repo(repo)
        records: list[TagRecord] = []
        for name in sorted(gitrepo.references):
            if not name.startswith("refs/tags/"):
                continue
            obj = gitrepo.references[name].peel()
            target = gitrepo[gitrepo.references[name].target]
            if target.type == self._pygit2.GIT_OBJECT_TAG:
                when, offset = target.tagger.time, target.tagger.offset
            else:
                when, offset = obj.committer.time, obj.committer.offset
            records.append(
                TagRecord(
                    name=name[len("refs/tags/") :],
                    sha=str(obj.id),
                    date=_iso(when, offset),
                )
            )
        return records

    def blame(self, repo: Path, rel_path: str) -> list[tuple[str, int]] | None:
        try:
            gitrepo = self._repo(repo)
            blame = gitrepo.blame(rel_path)
        except (KeyError, ValueError, GitError, self._pygit2.GitError):
            return None
        lines: list[tuple[str, int]] = []
        for hunk in blame:
            commit = gitrepo[hunk.final_commit_id]
            author = commit.author
            lines.extend((author.name, author.time) for _ in range(hunk.lines_in_hunk))
        return lines

    # -- object mining ---------------------------------------------------------

    def blobs(self, repo: Path) -> list[BlobRecord]:
        """Every blob reachable from any ref, with one example path, sorted
        by sha (the same contract as the rev-list + cat-file join)."""
        gitrepo = self._repo(repo)
        paths: dict[str, str] = {}
        seen_trees: set[str] = set()
        seen_commits: set[str] = set()
        for name in gitrepo.references:
            try:
                tip = gitrepo.references[name].peel(self._pygit2.Commit)
            except (self._pygit2.GitError, self._pygit2.InvalidSpecError):
                continue
            for commit in gitrepo.walk(tip.id, self._pygit2.GIT_SORT_NONE):
                if str(commit.id) in seen_commits:
                    continue
                seen_commits.add(str(commit.id))
                self._walk_tree(gitrepo, commit.tree, "", paths, seen_trees)
        records = [
            BlobRecord(sha=sha, path=path, size_bytes=gitrepo[sha].size)
            for sha, path in paths.items()
        ]
        records.sort(key=lambda b: b.sha)
        return records

    def _walk_tree(
        self,
        gitrepo: Any,
        tree: Any,
        prefix: str,
        paths: dict[str, str],
        seen_trees: set[str],
    ) -> None:
        if str(tree.id) in seen_trees:
            return
        seen_trees.add(str(tree.id))
        for entry in tree:
            rel = f"{prefix}{entry.name}"
            if entry.type_str == "tree":
                self._walk_tree(gitrepo, gitrepo[entry.id], f"{rel}/", paths, seen_trees)
            elif entry.type_str == "blob":
                paths.setdefault(str(entry.id), rel)
