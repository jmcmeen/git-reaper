"""Scry: the vision between two refs."""

from __future__ import annotations

import pytest

from git_reaper.core.scry import scry
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import render_scry
from git_reaper.gitio import GitError

ALICE = ("Alice", "alice@example.com")
CAROL = ("Carol", "carol@example.com")

SCRIPT = [
    {
        "message": "seed",
        "when": "2020-01-01T00:00:00+00:00",
        "author": ALICE,
        "write": {"a.py": "x = 1\n"},
        "tag": "v1",
    },
    {
        "message": "grow",
        "when": "2020-02-01T00:00:00+00:00",
        "author": ALICE,
        "write": {"a.py": "x = 1\ny = 2\n"},
    },
    {
        "message": "newcomer",
        "when": "2020-03-01T00:00:00+00:00",
        "author": CAROL,
        "write": {"b.py": "z = 3\n"},
        "tag": "v2",
    },
]


@pytest.fixture
def vision(make_history):
    repo = resolve_source(str(make_history(SCRIPT))).repo
    return scry(repo, "v1", "v2", generated="2026-07-01T00:00:00Z")


def test_scry_counts_the_range(vision):
    assert vision.commits == 2
    assert vision.insertions == 2 and vision.deletions == 0
    assert {d.path for d in vision.files} == {"a.py", "b.py"}


def test_scry_sees_who_did_the_changing(vision):
    assert {s.author for s in vision.souls} == {"Alice", "Carol"}
    assert vision.new_souls == ["Carol"]  # Alice existed before v1


def test_scry_render(vision):
    text = render_scry(vision)
    assert "v1 .. v2" in text and "new souls: Carol" in text


def test_scry_limit(make_history):
    repo = resolve_source(str(make_history(SCRIPT))).repo
    assert len(scry(repo, "v1", "v2", limit=1).files) == 1


def test_scry_refuses_plain_folders(make_dir):
    with pytest.raises(GitError):
        scry(resolve_source(str(make_dir({"a.md": "x\n"}))).repo, "v1", "v2")
