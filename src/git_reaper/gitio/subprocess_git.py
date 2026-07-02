"""Default git backend: shell out to the real git.

Zero heavy dependencies and behavior that matches git exactly, at the cost
of requiring git on PATH (which `reaper pulse` checks).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import cached_property
from pathlib import Path

from git_reaper.gitio.backend import (
    BranchRecord,
    DeadFileRecord,
    FileChange,
    GitBackend,
    GitCommit,
    GitError,
    TagRecord,
)

# Control chars as field/record separators: they never appear in commit
# content, so a multiline body can't break the parse the way a naive newline
# split would. RS bounds each commit; US bounds fields within it.
_RS = "\x1e"
_US = "\x1f"
_LOG_FORMAT = f"{_RS}%H{_US}%an{_US}%ae{_US}%at{_US}%aI{_US}%s{_US}%b{_US}"
_NUMSTAT = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")


class SubprocessGit(GitBackend):
    @cached_property
    def _git(self) -> str | None:
        """Resolved git executable, looked up once per backend instance."""
        return shutil.which("git")

    def _require_git(self) -> str:
        if self._git is None:
            raise GitError("git is not on PATH; install git or run `reaper pulse` for details")
        return self._git

    def _run(self, args: list[str], cwd: Path | None = None, check: bool = True) -> str:
        proc = subprocess.run(
            [self._require_git(), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            where = f" (in {cwd})" if cwd else ""
            raise GitError(
                f"git {' '.join(args)} failed{where}: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout

    def version(self) -> str | None:
        if self._git is None:
            return None
        return self._run(["--version"]).strip()

    def is_repo(self, path: Path) -> bool:
        if self._git is None or not path.is_dir():
            return False
        proc = subprocess.run(
            [self._git, "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def clone(self, url: str, dest: Path, depth: int | None = 1, ref: str | None = None) -> None:
        args = ["clone"]
        if depth:
            args += ["--depth", str(depth)]
        if ref:
            args += ["--branch", ref]
        args += [url, str(dest)]
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._run(args)

    def fetch(self, repo: Path, ref: str | None = None, depth: int | None = 1) -> None:
        args = ["fetch"]
        if depth:
            args += ["--depth", str(depth)]
        args.append("origin")
        if ref:
            args.append(ref)
        self._run(args, cwd=repo)

    def checkout(self, repo: Path, ref: str) -> None:
        # Try the local name first, then FETCH_HEAD for shallow single-ref fetches.
        proc = subprocess.run(
            [self._require_git(), "checkout", ref], cwd=repo, capture_output=True, text=True
        )
        if proc.returncode != 0:
            self._run(["checkout", "FETCH_HEAD"], cwd=repo)

    def head_sha(self, repo: Path) -> str | None:
        proc = subprocess.run(
            [self._require_git(), "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def blame(self, repo: Path, rel_path: str) -> list[tuple[str, int]] | None:
        if self._git is None:
            return None
        proc = subprocess.run(
            [self._git, "blame", "--line-porcelain", "--", rel_path],
            cwd=repo,
            capture_output=True,
            text=True,
            errors="replace",
        )
        if proc.returncode != 0:
            return None
        lines: list[tuple[str, int]] = []
        author, when = "", 0
        for raw in proc.stdout.split("\n"):
            if raw.startswith("author "):
                author = raw[7:]
            elif raw.startswith("author-time "):
                when = int(raw[12:])
            elif raw.startswith("\t"):
                lines.append((author, when))
        return lines

    def current_branch(self, repo: Path) -> str | None:
        proc = subprocess.run(
            [self._require_git(), "symbolic-ref", "--short", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    # -- history mining (Phase 3) ------------------------------------------

    @staticmethod
    def _parse_numstat(blob: str) -> list[FileChange]:
        files = []
        for line in blob.split("\n"):
            m = _NUMSTAT.match(line)
            if not m:
                continue
            ins = None if m.group(1) == "-" else int(m.group(1))
            dels = None if m.group(2) == "-" else int(m.group(2))
            files.append(FileChange(path=m.group(3), insertions=ins, deletions=dels))
        return files

    @classmethod
    def _parse_log(cls, out: str) -> list[GitCommit]:
        commits: list[GitCommit] = []
        for record in out.split(_RS):
            if _US not in record:
                continue  # the empty chunk before the first RS
            parts = record.split(_US)
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
                    files=cls._parse_numstat(parts[7]),
                )
            )
        return commits

    def log(
        self, repo: Path, ref: str | None = None, max_count: int | None = None
    ) -> list[GitCommit]:
        args = ["log", f"--pretty=format:{_LOG_FORMAT}", "--numstat", "--no-renames"]
        if max_count is not None:
            args.append(f"--max-count={max_count}")
        if ref:
            args.append(ref)
        return self._parse_log(self._run(args, cwd=repo))

    def file_log(self, repo: Path, rel_path: str, follow: bool = True) -> list[GitCommit]:
        args = ["log", f"--pretty=format:{_LOG_FORMAT}", "--numstat"]
        if follow:
            args.append("--follow")
        args += ["--", rel_path]
        return self._parse_log(self._run(args, cwd=repo))

    def rename_history(self, repo: Path, rel_path: str) -> list[str]:
        out = self._run(["log", "--follow", "--name-status", "--format=", "--", rel_path], cwd=repo)
        seen: list[str] = []
        for line in out.split("\n"):
            if line.startswith("R"):  # Rnnn\told\tnew
                cols = line.split("\t")
                if len(cols) >= 3 and cols[1] not in seen and cols[1] != rel_path:
                    seen.append(cols[1])
        return seen

    def deleted_files(self, repo: Path) -> list[DeadFileRecord]:
        fmt = f"{_RS}%H{_US}%aI{_US}%an"
        # --no-renames so a rename reads as a death of the old path (matching
        # log()); otherwise git's default rename detection hides it as an R.
        out = self._run(
            ["log", "--diff-filter=D", "--name-only", "--no-renames", f"--pretty=format:{fmt}"],
            cwd=repo,
        )
        dead: list[DeadFileRecord] = []
        seen: set[str] = set()
        for record in out.split(_RS):
            if _US not in record:
                continue
            header, _, body = record.partition("\n")
            sha, date, author = header.split(_US)
            for path in body.split("\n"):
                path = path.strip()
                if path and path not in seen:
                    seen.add(path)
                    dead.append(DeadFileRecord(path=path, sha=sha, date=date, author=author))
        return dead

    def show_file(self, repo: Path, rev: str, rel_path: str) -> bytes | None:
        proc = subprocess.run(
            [self._require_git(), "show", f"{rev}:{rel_path}"],
            cwd=repo,
            capture_output=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout

    def branches(self, repo: Path) -> list[BranchRecord]:
        fmt = _US.join(
            [
                "%(refname:short)",
                "%(committerdate:unix)",
                "%(committerdate:iso-strict)",
                "%(authorname)",
                "%(upstream:track)",
            ]
        )
        out = self._run(["for-each-ref", f"--format={fmt}", "refs/heads"], cwd=repo)
        merged = self._merged_branches(repo)
        branches: list[BranchRecord] = []
        for line in out.split("\n"):
            if _US not in line:
                continue
            name, when, iso, author, track = line.split(_US)
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

    def _merged_branches(self, repo: Path) -> set[str]:
        proc = subprocess.run(
            [self._require_git(), "branch", "--merged"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return set()
        return {line.lstrip("* ").strip() for line in proc.stdout.split("\n") if line.strip()}

    def tags(self, repo: Path) -> list[TagRecord]:
        fmt = _US.join(
            ["%(refname:short)", "%(objectname)", "%(*objectname)", "%(creatordate:iso-strict)"]
        )
        out = self._run(["for-each-ref", f"--format={fmt}", "refs/tags"], cwd=repo)
        tags: list[TagRecord] = []
        for line in out.split("\n"):
            if _US not in line:
                continue
            name, obj, deref, date = line.split(_US)
            tags.append(TagRecord(name=name, sha=deref or obj, date=date))
        return tags
