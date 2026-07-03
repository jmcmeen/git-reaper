"""Effigy: the measured portrait and its SVG rendering."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import effigy as effigy_core
from git_reaper.formatters import svgfmt
from git_reaper.gitio import GitError
from git_reaper.models import RepoRef

runner = CliRunner()

PINNED = "2020-06-06T06:06:06Z"


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


def test_effigy_measures_the_portrait(necropolis):
    result = effigy_core.effigy(ref(necropolis), generated=PINNED)
    assert result.name == "necropolis"
    assert result.commits == 5
    assert result.born.startswith("2020-01-06")
    assert result.souls[0].name == "Alice"  # most commits first
    assert len(result.heatmap) == 7 and len(result.heatmap[0]) == 24
    assert result.witching_hour == "Mon 02:00"
    slices = {s.name for s in result.slices}
    assert "src" in slices and "docs" in slices


def test_effigy_on_a_plain_folder_errors(make_dir):
    folder = make_dir({"a.md": "hi\n"})
    with pytest.raises(GitError):
        effigy_core.effigy(ref(folder))


def test_effigy_svg_is_wellformed_and_escaped(necropolis):
    result = effigy_core.effigy(ref(necropolis), generated=PINNED)
    result.name = 'grave & <mausoleum> "deluxe"'
    svg = svgfmt.render_effigy(result)
    root = ET.fromstring(svg)  # parses -> well-formed XML
    assert root.tag.endswith("svg")
    assert "grave &amp; &lt;mausoleum&gt;" in svg
    assert "schema:    effigy/v1" in svg  # the stamp rides in the <desc>


def test_effigy_svg_is_deterministic(necropolis):
    result = effigy_core.effigy(ref(necropolis), generated=PINNED)
    again = effigy_core.effigy(ref(necropolis), generated=PINNED)
    assert svgfmt.render_effigy(result) == svgfmt.render_effigy(again)


def test_effigy_cli_svg_and_json(necropolis, tmp_path):
    out = tmp_path / "portrait.svg"
    result = runner.invoke(app, ["--plain", "effigy", str(necropolis), "--out", str(out)])
    assert result.exit_code == 0
    assert out.read_text(encoding="utf-8").startswith("<svg")

    as_json = runner.invoke(app, ["--plain", "effigy", str(necropolis), "--format", "json"])
    assert as_json.exit_code == 0
    assert '"witching_hour"' in as_json.stdout

    bad = runner.invoke(app, ["--plain", "effigy", str(necropolis), "--format", "csv"])
    assert bad.exit_code == 1
