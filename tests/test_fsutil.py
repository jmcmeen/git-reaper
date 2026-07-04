"""fsutil: size parsing and rendering."""

from __future__ import annotations

import os
import tarfile
import zipfile

import pytest

from git_reaper import fsutil


def test_parse_size_units():
    assert fsutil.parse_size("1024") == 1024
    assert fsutil.parse_size("1MB") == 1000**2
    assert fsutil.parse_size("512KiB") == 512 * 1024
    assert fsutil.parse_size("1.5 GB") == int(1.5 * 1000**3)
    assert fsutil.parse_size("2k") == 2000  # bare K/M/G/T means the SI unit


def test_parse_size_rejects_nonsense():
    for bad in ("a lot", "MB", "-5MB"):
        with pytest.raises(ValueError):
            fsutil.parse_size(bad)


def test_parse_size_rejects_units_the_regex_allows():
    # '1Ki' matches the size regex but is not a real unit; it must raise the
    # documented ValueError, not a KeyError from the unit table.
    for bad in ("1Ki", "1IB", "3I"):
        with pytest.raises(ValueError):
            fsutil.parse_size(bad)


def test_force_rmtree_removes_readonly_files(tmp_path):
    # Git marks object files read-only; on Windows plain rmtree chokes on
    # them. force_rmtree must clear the bit and finish the job.
    crypt = tmp_path / "crypt"
    (crypt / "objects").mkdir(parents=True)
    obj = crypt / "objects" / "50052b2e"
    obj.write_bytes(b"x")
    obj.chmod(0o444)
    fsutil.force_rmtree(crypt)
    assert not crypt.exists()


def test_human_size():
    assert fsutil.human_size(340) == "340 B"
    assert fsutil.human_size(1_200_000) == "1.2 MB"


def _tree(tmp_path, name="loot"):
    root = tmp_path / name
    (root / "sub").mkdir(parents=True)
    # write_text would translate \n -> \r\n on Windows, making the packed
    # bytes (and this test's exact-byte assertions) platform-dependent.
    (root / "a.md").write_bytes(b"a\n")
    (root / "sub" / "b.bin").write_bytes(b"\x00\x01\x02")
    return root


_EXT = {"zip": ".zip", "tar": ".tar", "tar.gz": ".tar.gz"}


@pytest.mark.parametrize("fmt", fsutil.ARCHIVE_FORMATS)
def test_make_archive_round_trips_the_tree(tmp_path, fmt):
    root = _tree(tmp_path)
    archive = fsutil.make_archive(root, fmt)
    assert archive == root.with_name(root.name + _EXT[fmt])
    assert archive.is_file()
    # source_dir is left untouched; the caller decides whether to remove it.
    assert root.is_dir()

    if fmt == "zip":
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            assert "loot/a.md" in names and "loot/sub/b.bin" in names
            assert zf.read("loot/a.md") == b"a\n"
            assert zf.read("loot/sub/b.bin") == b"\x00\x01\x02"
    else:
        mode = "r:gz" if fmt == "tar.gz" else "r"
        with tarfile.open(archive, mode) as tar:
            names = tar.getnames()
            assert "loot/a.md" in names and "loot/sub/b.bin" in names
            member = tar.extractfile("loot/a.md")
            assert member is not None and member.read() == b"a\n"


@pytest.mark.parametrize("fmt", fsutil.ARCHIVE_FORMATS)
def test_make_archive_is_byte_identical_across_runs(tmp_path, fmt):
    one = _tree(tmp_path / "one", name="loot")
    two = _tree(tmp_path / "two", name="loot")
    first = fsutil.make_archive(one, fmt)
    second = fsutil.make_archive(two, fmt)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_make_archive_skips_symlinks(tmp_path):
    root = _tree(tmp_path)
    (root / "escape").symlink_to(root / "a.md")
    archive = fsutil.make_archive(root, "zip")
    with zipfile.ZipFile(archive) as zf:
        assert not any("escape" in name for name in zf.namelist())


def test_make_archive_rejects_unknown_format(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(ValueError):
        fsutil.make_archive(root, "rar")
