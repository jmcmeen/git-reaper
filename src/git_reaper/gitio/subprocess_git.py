"""Default git backend: shell out to the real git.

Zero heavy dependencies and behavior that matches git exactly, at the cost
of requiring git on PATH (which `reaper pulse` checks).
"""

from __future__ import annotations

import shutil
import subprocess
from functools import cached_property
from pathlib import Path

from git_reaper.gitio import logparse
from git_reaper.gitio.backend import (
    BlobRecord,
    BranchRecord,
    DeadFileRecord,
    FileEventRecord,
    GitBackend,
    GitCommit,
    GitError,
    TagRecord,
)


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
        elif self._is_shallow(repo):
            # A full-depth fetch over a shallow clone must unshallow it, or the
            # history commands would silently see only the tip commit.
            args.append("--unshallow")
        args.append("origin")
        if ref:
            args.append(ref)
        self._run(args, cwd=repo)

    def _is_shallow(self, repo: Path) -> bool:
        proc = subprocess.run(
            [self._require_git(), "rev-parse", "--is-shallow-repository"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"

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
        return logparse.parse_blame(proc.stdout)

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
    # Command shapes and parsing are shared (gitio.logparse); this backend
    # only supplies the transport (subprocess).

    def log(
        self, repo: Path, ref: str | None = None, max_count: int | None = None
    ) -> list[GitCommit]:
        return logparse.parse_log(self._run(logparse.log_args(ref, max_count), cwd=repo))

    def file_log(self, repo: Path, rel_path: str, follow: bool = True) -> list[GitCommit]:
        return logparse.parse_log(self._run(logparse.file_log_args(rel_path, follow), cwd=repo))

    def rename_history(self, repo: Path, rel_path: str) -> list[str]:
        return logparse.parse_renames(self._run(logparse.rename_args(rel_path), cwd=repo), rel_path)

    def deleted_files(self, repo: Path) -> list[DeadFileRecord]:
        return logparse.parse_deleted(self._run(logparse.deleted_args(), cwd=repo))

    def pickaxe(
        self, repo: Path, needle: str, regex: bool = False, rel_path: str | None = None
    ) -> list[GitCommit]:
        return logparse.parse_log(
            self._run(logparse.pickaxe_args(needle, regex, rel_path), cwd=repo)
        )

    def file_events(self, repo: Path) -> list[FileEventRecord]:
        return logparse.parse_events(self._run(logparse.events_args(), cwd=repo))

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
        out = self._run(logparse.branch_ref_args(), cwd=repo)
        merged = self._merged_branches(repo)
        return logparse.parse_branches(out, merged)

    def _merged_branches(self, repo: Path) -> set[str]:
        proc = subprocess.run(
            [self._require_git(), "branch", "--merged"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return set()
        return logparse.parse_merged(proc.stdout)

    def tags(self, repo: Path) -> list[TagRecord]:
        return logparse.parse_tags(self._run(logparse.tag_ref_args(), cwd=repo))

    # -- object mining (Phase 5) ---------------------------------------------

    def blobs(self, repo: Path, ref: str | None = None) -> list[BlobRecord]:
        return logparse.parse_blobs(
            self._run(logparse.object_list_args(ref), cwd=repo),
            self._run(logparse.batch_check_args(), cwd=repo),
        )

    def cat_blob(self, repo: Path, sha: str) -> bytes | None:
        proc = subprocess.run(
            [self._require_git(), "cat-file", "blob", sha],
            cwd=repo,
            capture_output=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout

    def blob_commit(self, repo: Path, sha: str, path: str) -> tuple[str, str, str] | None:
        proc = subprocess.run(
            [self._require_git(), *logparse.blob_commit_args(sha, path)],
            cwd=repo,
            capture_output=True,
            text=True,
            errors="replace",
        )
        if proc.returncode != 0:
            return None
        return logparse.parse_blob_commit(proc.stdout)
