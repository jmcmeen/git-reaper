"""fsutil: size parsing and rendering."""

from __future__ import annotations

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


def test_human_size():
    assert fsutil.human_size(340) == "340 B"
    assert fsutil.human_size(1_200_000) == "1.2 MB"
