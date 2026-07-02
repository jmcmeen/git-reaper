"""HTML reports: self-contained, escaped, dark."""

from __future__ import annotations

from git_reaper.core import rules
from git_reaper.core.census import census
from git_reaper.core.dedupe import bloat, doppelgangers
from git_reaper.core.history import haunt
from git_reaper.core.source import resolve_source
from git_reaper.formatters import htmlfmt


def test_census_page_is_self_contained(make_dir):
    repo = resolve_source(str(make_dir({"a.py": "x = 1\n", "b.md": "# hi\n"}))).repo
    page = htmlfmt.render("census", census(repo, generated="2026-07-01T00:00:00Z"))
    assert page.startswith("<!DOCTYPE html>")
    assert "<style>" in page and "src=" not in page and "http" not in page.split("invoked:")[0]
    assert ".py" in page and "generated: 2026-07-01T00:00:00Z" in page


def test_html_is_escaped(make_dir):
    files = {"evil.py": "# TODO <script>alert('boo')</script>\n"}
    repo = resolve_source(str(make_dir(files))).repo
    from git_reaper.core.scan import unfinished

    page = htmlfmt.render("unfinished", unfinished(repo))
    assert "<script>" not in page.split("</style>")[1]  # only our own tags survive
    assert "&lt;script&gt;" in page


def test_bars_scale_to_the_peak(make_repo):
    repo = resolve_source(str(make_repo({"hot.py": "x\n", "cold.py": "y\n"}))).repo
    page = htmlfmt.render("haunt", haunt(repo))
    assert 'class="num bar"' in page and "width:100.0%" in page


def test_exhume_page_marks_severity(make_repo):
    repo = resolve_source(str(make_repo({"leak.txt": "AKIAABCDEFGHIJKLMNOP\n"}))).repo
    page = htmlfmt.render("exhume", rules.exhume(repo))
    assert 'class="severity-high"' in page
    assert "AKIA...MNOP" in page and "AKIAABCDEFGHIJKLMNOP" not in page


def test_every_supported_command_renders(make_repo):
    # a smoke pass over the shared table machinery for the folder commands
    repo = resolve_source(str(make_repo({"a.txt": "same\n", "b.txt": "same\n"}))).repo
    for command, result in (
        ("doppelgangers", doppelgangers(repo)),
        ("bloat", bloat(repo)),
    ):
        page = htmlfmt.render(command, result)
        assert page.startswith("<!DOCTYPE html>"), command
        assert "</html>" in page


def test_supported_registry_matches_renderers():
    assert "census" in htmlfmt.SUPPORTED and "omens" in htmlfmt.SUPPORTED
