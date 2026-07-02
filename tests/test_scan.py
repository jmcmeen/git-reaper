"""Unfinished business: marker scanning, blame authors, ages."""

from __future__ import annotations

from git_reaper.core.scan import unfinished
from git_reaper.core.source import resolve_source
from git_reaper.formatters import csvfmt, markdown

FILES = {
    "src/main.py": "x = 1\n# TODO: finish this ritual\ny = 2  # FIXME broken\n",
    "docs/notes.md": "HACK: hold it together with tape\nall done here\n",
    "clean.py": "print('nothing to see')\n",
}


def test_markers_found_with_lines_and_counts(make_dir):
    result = unfinished(resolve_source(str(make_dir(FILES))).repo)
    found = {(m.path, m.line, m.marker) for m in result.markers}
    assert ("src/main.py", 2, "TODO") in found
    assert ("src/main.py", 3, "FIXME") in found
    assert ("docs/notes.md", 1, "HACK") in found
    assert result.counts == {"TODO": 1, "FIXME": 1, "HACK": 1}
    todo = next(m for m in result.markers if m.marker == "TODO")
    assert todo.text == "finish this ritual"
    # plain folder: no repo, no blame, no author
    assert all(m.author is None for m in result.markers)


def test_blame_fills_authors_in_a_repo(make_repo):
    result = unfinished(resolve_source(str(make_repo(FILES))).repo, with_age=True)
    todo = next(m for m in result.markers if m.marker == "TODO")
    assert todo.author == "Test Ghost"
    assert todo.age_days is not None and todo.age_days >= 0


def test_unfinished_renders(make_dir):
    result = unfinished(
        resolve_source(str(make_dir(FILES))).repo, generated="2026-07-01T00:00:00Z"
    )
    md = markdown.render_unfinished(result)
    assert "schema:    unfinished/v1" in md
    assert "**TODO**: finish this ritual" in md
    csv_text = csvfmt.render_unfinished(result)
    assert csv_text.splitlines()[0] == "path,line,marker,text,author,age_days"
    assert "src/main.py,2,TODO,finish this ritual,," in csv_text
