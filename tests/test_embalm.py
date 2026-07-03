"""Embalm: the deterministic, provenance-stamped snapshot."""

from __future__ import annotations

import hashlib
import tarfile

from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import embalm as embalm_core
from git_reaper.models import RepoRef

runner = CliRunner()

PINNED = "2020-06-06T06:06:06Z"


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def test_embalm_preserves_the_tree_with_stamp_and_manifest(make_repo, tmp_path):
    root = make_repo({"README.md": "# hi\n", "src/a.py": "x = 1\n"}, name="mummy")
    out = tmp_path / "mummy.tar.gz"
    result = embalm_core.embalm(ref(root), out, generated=PINNED)
    assert result.files == 2
    assert out.is_file()
    with tarfile.open(out) as tar:
        names = tar.getnames()
        assert "mummy/README.md" in names and "mummy/src/a.py" in names
        stamp = tar.extractfile("mummy/PROVENANCE")
        assert stamp is not None and b"schema:    embalm/v1" in stamp.read()
        manifest = tar.extractfile("mummy/MANIFEST.sha256")
        assert manifest is not None
        lines = manifest.read().decode().strip().splitlines()
        digest = hashlib.sha256(b"# hi\n").hexdigest()
        assert f"{digest}  README.md" in lines


def test_embalm_is_byte_identical_across_runs(make_repo, tmp_path):
    root = make_repo({"a.md": "same\n", "b.py": "same\n"})
    one, two = tmp_path / "one.tar.gz", tmp_path / "two.tar.gz"
    first = embalm_core.embalm(ref(root), one, generated=PINNED)
    second = embalm_core.embalm(ref(root), two, generated=PINNED)
    assert one.read_bytes() == two.read_bytes()
    assert first.archive_sha256 == second.archive_sha256
    assert first.archive_sha256 == hashlib.sha256(one.read_bytes()).hexdigest()


def test_embalm_pins_timestamps_to_the_head_commit(necropolis, tmp_path):
    out = tmp_path / "necro.tar.gz"
    embalm_core.embalm(ref(necropolis), out, generated=PINNED)
    with tarfile.open(out) as tar:
        mtimes = {info.mtime for info in tar.getmembers()}
    # every entry carries the HEAD author time (2020-01-10T02:00:00Z), never the wall clock
    assert mtimes == {1578621600}


def test_embalm_works_on_a_plain_folder(make_dir, tmp_path):
    root = make_dir({"notes.txt": "plain\n"})
    out = tmp_path / "plain.tar.gz"
    result = embalm_core.embalm(ref(root), out, generated=PINNED)
    assert result.files == 1
    with tarfile.open(out) as tar:
        assert all(info.mtime == 0 for info in tar.getmembers())


def test_embalm_honors_excludes(make_repo, tmp_path):
    root = make_repo({"keep.md": "k\n", "skip.log": "s\n"})
    out = tmp_path / "kept.tar.gz"
    result = embalm_core.embalm(ref(root), out, excludes=["*.log"], generated=PINNED)
    assert result.files == 1
    with tarfile.open(out) as tar:
        assert all("skip.log" not in name for name in tar.getnames())


def test_embalm_cli_receipt(make_repo, tmp_path, monkeypatch):
    root = make_repo({"a.md": "hi\n"})
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--plain", "embalm", str(root), "--out", "corpse.tar.gz"])
    assert result.exit_code == 0
    assert "schema:    embalm/v1" in result.stdout
    assert "archive sha256" in result.stdout
    assert (tmp_path / "corpse.tar.gz").is_file()
