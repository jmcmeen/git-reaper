"""Default git backend: shell out to the real git.

Zero heavy dependencies and behavior that matches git exactly, at the cost
of requiring git on PATH (which `reaper pulse` checks).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from git_reaper.gitio.backend import GitBackend, GitError


class SubprocessGit(GitBackend):
    def _run(self, args: list[str], cwd: Path | None = None, check: bool = True) -> str:
        if shutil.which("git") is None:
            raise GitError("git is not on PATH; install git or run `reaper pulse` for details")
        proc = subprocess.run(
            ["git", *args],
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
        if shutil.which("git") is None:
            return None
        return self._run(["--version"]).strip()

    def is_repo(self, path: Path) -> bool:
        if shutil.which("git") is None or not path.is_dir():
            return False
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
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
        proc = subprocess.run(["git", "checkout", ref], cwd=repo, capture_output=True, text=True)
        if proc.returncode != 0:
            self._run(["checkout", "FETCH_HEAD"], cwd=repo)

    def head_sha(self, repo: Path) -> str | None:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def current_branch(self, repo: Path) -> str | None:
        proc = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None
