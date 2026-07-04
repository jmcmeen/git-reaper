"""Optional git backend built on GitPython (the ``git-reaper[git]`` extra).

GitPython still drives the git CLI under the hood, so this backend runs the
same commands as the subprocess one and reuses the shared parsers -- results
are byte-identical (the parity tests enforce it). What GitPython buys us is
convenient object access for the structural bits (clone, head, blobs) and a
home for callers who already depend on it. It is never imported unless
explicitly selected, so the base install stays free of the dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def _import_git() -> Any:
    """The `git` module, or a clear error if the [git] extra is missing."""
    try:
        import git

        return git
    except ImportError as exc:
        raise GitError("the GitPython backend needs the extra; install `git-reaper[git]`") from exc


class GitPythonGit(GitBackend):
    def __init__(self) -> None:
        self._git: Any = _import_git()

    def _repo(self, path: Path) -> Any:
        return self._git.Repo(path)

    def _exec(self, path: Path, args: list[str]) -> str:
        """Run a raw git command through GitPython and return its stdout."""
        out: str = self._repo(path).git.execute(["git", *args])
        return out

    def version(self) -> str | None:
        try:
            out: str = self._git.Git().version()
            return out
        except Exception:  # pragma: no cover - git missing but GitPython present
            return None

    def is_repo(self, path: Path) -> bool:
        if not path.is_dir():
            return False
        try:
            self._git.Repo(path, search_parent_directories=True)
            return True
        except (self._git.InvalidGitRepositoryError, self._git.NoSuchPathError):
            return False

    def clone(self, url: str, dest: Path, depth: int | None = 1, ref: str | None = None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, object] = {}
        if depth:
            kwargs["depth"] = depth
        if ref:
            kwargs["branch"] = ref
        try:
            self._git.Repo.clone_from(url, str(dest), **kwargs)
        except self._git.GitCommandError as exc:
            raise GitError(f"git clone failed: {exc}") from exc

    def fetch(self, repo: Path, ref: str | None = None, depth: int | None = 1) -> None:
        args = ["fetch"]
        if depth:
            args += ["--depth", str(depth)]
        elif self._is_shallow(repo):
            args.append("--unshallow")
        args.append("origin")
        if ref:
            args.append(ref)
        try:
            self._exec(repo, args)
        except self._git.GitCommandError as exc:
            raise GitError(f"git fetch failed: {exc}") from exc

    def _is_shallow(self, repo: Path) -> bool:
        try:
            return self._exec(repo, ["rev-parse", "--is-shallow-repository"]).strip() == "true"
        except self._git.GitCommandError:
            return False

    def checkout(self, repo: Path, ref: str) -> None:
        try:
            self._repo(repo).git.checkout(ref)
        except self._git.GitCommandError:
            try:
                self._repo(repo).git.checkout("FETCH_HEAD")
            except self._git.GitCommandError as exc:
                raise GitError(f"git checkout {ref} failed: {exc}") from exc

    def head_sha(self, repo: Path) -> str | None:
        try:
            sha: str = self._repo(repo).head.commit.hexsha
            return sha
        except Exception:
            return None

    def current_branch(self, repo: Path) -> str | None:
        try:
            name: str = self._repo(repo).active_branch.name
            return name or None
        except (TypeError, self._git.InvalidGitRepositoryError, self._git.NoSuchPathError):
            return None

    def blame(self, repo: Path, rel_path: str) -> list[tuple[str, int]] | None:
        try:
            out = self._exec(repo, ["blame", "--line-porcelain", "--", rel_path])
        except (
            self._git.GitCommandError,
            self._git.InvalidGitRepositoryError,
            self._git.NoSuchPathError,
        ):
            return None
        return logparse.parse_blame(out)

    # -- history mining (Phase 3) ------------------------------------------

    def log(
        self, repo: Path, ref: str | None = None, max_count: int | None = None
    ) -> list[GitCommit]:
        return logparse.parse_log(self._exec(repo, logparse.log_args(ref, max_count)))

    def file_log(self, repo: Path, rel_path: str, follow: bool = True) -> list[GitCommit]:
        return logparse.parse_log(self._exec(repo, logparse.file_log_args(rel_path, follow)))

    def rename_history(self, repo: Path, rel_path: str) -> list[str]:
        return logparse.parse_renames(self._exec(repo, logparse.rename_args(rel_path)), rel_path)

    def deleted_files(self, repo: Path) -> list[DeadFileRecord]:
        return logparse.parse_deleted(self._exec(repo, logparse.deleted_args()))

    def pickaxe(
        self, repo: Path, needle: str, regex: bool = False, rel_path: str | None = None
    ) -> list[GitCommit]:
        return logparse.parse_log(self._exec(repo, logparse.pickaxe_args(needle, regex, rel_path)))

    def file_events(self, repo: Path) -> list[FileEventRecord]:
        return logparse.parse_events(self._exec(repo, logparse.events_args()))

    def show_file(self, repo: Path, rev: str, rel_path: str) -> bytes | None:
        try:
            blob = self._repo(repo).commit(rev).tree / rel_path
        except (KeyError, self._git.BadName, ValueError):
            return None
        data: bytes = blob.data_stream.read()
        return data

    def branches(self, repo: Path) -> list[BranchRecord]:
        out = self._exec(repo, logparse.branch_ref_args())
        merged = logparse.parse_merged(self._repo(repo).git.branch("--merged"))
        return logparse.parse_branches(out, merged)

    def tags(self, repo: Path) -> list[TagRecord]:
        return logparse.parse_tags(self._exec(repo, logparse.tag_ref_args()))

    # -- object mining (Phase 5) ---------------------------------------------

    def blobs(self, repo: Path, ref: str | None = None) -> list[BlobRecord]:
        try:
            objects = self._exec(repo, logparse.object_list_args(ref))
        except self._git.GitCommandError as exc:
            raise GitError(f"git rev-list failed (in {repo}): {exc}") from exc
        return logparse.parse_blobs(objects, self._exec(repo, logparse.batch_check_args()))

    def cat_blob(self, repo: Path, sha: str) -> bytes | None:
        try:
            data: bytes = self._repo(repo).odb.stream(bytes.fromhex(sha)).read()
            return data
        except Exception:
            return None

    def blob_commit(self, repo: Path, sha: str, path: str) -> tuple[str, str, str] | None:
        try:
            out = self._exec(repo, logparse.blob_commit_args(sha, path))
        except self._git.GitCommandError:
            return None
        return logparse.parse_blob_commit(out)
