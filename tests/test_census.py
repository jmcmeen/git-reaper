"""Census: counts, sizes, languages, and the csv/md renders."""

from __future__ import annotations

from git_reaper.core.census import census
from git_reaper.core.source import resolve_source
from git_reaper.formatters import csvfmt, markdown

FILES = {
    "README.md": "# top\n",
    "docs/guide.md": "read me\nplease\n",
    "src/main.py": "print('hi')\n",
    "blob.bin": b"\x00\x01\x02\x03",
}


def test_census_counts_and_groups(make_dir):
    result = census(resolve_source(str(make_dir(FILES))).repo, generated="2026-07-01T00:00:00Z")
    by_ext = {stat.extension: stat for stat in result.extensions}
    assert by_ext[".md"].files == 2
    assert by_ext[".md"].language == "Markdown"
    assert by_ext[".md"].line_count == 3
    assert by_ext[".py"].files == 1
    assert result.total_files == 4
    # binary: weighed, but no lines and no tokens
    assert by_ext[".bin"].size_bytes == 4
    assert by_ext[".bin"].line_count == 0
    assert by_ext[".bin"].token_estimate == 0
    # heaviest first
    sizes = [stat.size_bytes for stat in result.extensions]
    assert sizes == sorted(sizes, reverse=True)


def test_census_renders(make_dir):
    result = census(resolve_source(str(make_dir(FILES))).repo, generated="2026-07-01T00:00:00Z")
    md = markdown.render_census(result)
    assert "schema:    census/v1" in md
    assert "| .md | Markdown | 2 " in md
    csv_text = csvfmt.render_census(result)
    assert csv_text.splitlines()[0] == "extension,language,files,size_bytes,lines,token_estimate"
    assert any(line.startswith(".md,Markdown,2,") for line in csv_text.splitlines())
