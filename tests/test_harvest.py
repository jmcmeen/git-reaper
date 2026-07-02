"""Harvest: gathering, skipping with receipts, determinism, provenance."""

from __future__ import annotations

import io

import pytest

from git_reaper.core.harvest import CapExceeded, harvest
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import write_harvest

FILES = {
    "README.md": "# The Crypt\n",
    "docs/guide.md": "read me\n",
    "docs/notes.txt": "not markdown\n",
    "src/main.py": "print('alive')\n",
    "assets/logo.bin": b"\x00\x01\x02binary",
}


def _render(result) -> str:
    buf = io.StringIO()
    write_harvest(result, buf)
    return buf.getvalue()


def test_harvest_defaults_to_markdown(make_repo):
    repo = resolve_source(str(make_repo(FILES))).repo
    result = harvest(repo)
    assert [f.path for f in result.files] == ["README.md", "docs/guide.md"]
    assert result.total_lines == 2
    assert result.provenance.files == 2
    assert result.provenance.sha is not None


def test_harvest_patterns_and_excludes(make_repo):
    repo = resolve_source(str(make_repo(FILES))).repo
    result = harvest(repo, patterns=("*.md", "*.py"), excludes=["docs/"])
    assert [f.path for f in result.files] == ["README.md", "src/main.py"]


def test_harvest_skips_binary_with_reason(make_repo):
    repo = resolve_source(str(make_repo(FILES))).repo
    result = harvest(repo, patterns=("*",))
    skipped = {entry.path: entry.skip_reason for entry in result.skipped}
    assert skipped["assets/logo.bin"] == "binary"


def test_harvest_size_cap_skips_with_receipt(make_repo):
    files = dict(FILES, **{"big.md": "x" * 10_000 + "\n"})
    repo = resolve_source(str(make_repo(files))).repo
    result = harvest(repo, max_file_size=1_000)
    assert "big.md" not in [f.path for f in result.files]
    assert any(e.path == "big.md" and "size cap" in (e.skip_reason or "") for e in result.skipped)


def test_harvest_total_cap_raises(make_repo):
    repo = resolve_source(str(make_repo(FILES))).repo
    with pytest.raises(CapExceeded):
        harvest(repo, patterns=("*",), max_total_size=5)


def test_harvest_respects_gitignore_and_reaperignore(make_repo):
    files = dict(
        FILES,
        **{
            ".gitignore": "ignored.md\n",
            ".reaperignore": "docs/\n",
            "ignored.md": "buried\n",
        },
    )
    repo = resolve_source(str(make_repo(files))).repo
    result = harvest(repo)
    assert [f.path for f in result.files] == ["README.md"]


def test_harvest_works_on_plain_directory(make_dir):
    repo = resolve_source(str(make_dir(FILES))).repo
    result = harvest(repo)
    assert repo.sha is None
    assert [f.path for f in result.files] == ["README.md", "docs/guide.md"]


def test_artifact_is_deterministic_and_delimited(make_repo):
    repo = resolve_source(str(make_repo(FILES))).repo
    kwargs = {"invoked": "reaper harvest .", "generated": "2026-07-01T00:00:00Z"}
    first = _render(harvest(repo, **kwargs))
    second = _render(harvest(repo, **kwargs))
    assert first == second
    assert "schema:    harvest/v1" in first
    assert "## docs/guide.md" in first
    assert "<!-- end docs/guide.md -->" in first
    # tree order is sorted -> README before docs
    assert first.index("## README.md") < first.index("## docs/guide.md")


def test_artifact_terminates_unterminated_final_line(make_dir):
    repo = resolve_source(str(make_dir({"a.md": "no newline at end"}))).repo
    text = _render(harvest(repo))
    assert "no newline at end\n<!-- end a.md -->" in text
