"""Plague: manifest parsing offline, oracle consultation via a fake wire."""

from __future__ import annotations

from git_reaper.core.plague import plague
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import render_plague

PYPROJECT = """
[project]
name = "victim"
dependencies = ["requests==2.31.0", "click>=8.0"]

[project.optional-dependencies]
dev = ["pytest==8.0.0"]
"""

PACKAGE_JSON = """
{
  "dependencies": {"left-pad": "1.3.0", "lodash": "^4.17.0"},
  "devDependencies": {"jest": "29.7.0"}
}
"""


def _repo(make_dir, files):
    return resolve_source(str(make_dir(files))).repo


def test_offline_parses_every_manifest(make_dir):
    repo = _repo(
        make_dir,
        {
            "requirements.txt": "flask==3.0.0\n# a comment\ndjango>=4\n-r other.txt\n",
            "pyproject.toml": PYPROJECT,
            "package.json": PACKAGE_JSON,
        },
    )
    result = plague(repo, offline=True)
    assert not result.checked and result.afflictions == []
    by_name = {(d.name, d.manifest): d for d in result.dependencies}
    assert by_name[("flask", "requirements.txt")].pinned
    assert by_name[("flask", "requirements.txt")].version == "3.0.0"
    assert not by_name[("django", "requirements.txt")].pinned
    assert by_name[("requests", "pyproject.toml")].pinned
    assert not by_name[("click", "pyproject.toml")].pinned
    assert by_name[("pytest", "pyproject.toml")].pinned  # optional-dependencies count
    assert by_name[("left-pad", "package.json")].pinned
    assert not by_name[("lodash", "package.json")].pinned  # ^range is not a pin
    assert by_name[("left-pad", "package.json")].ecosystem == "npm"
    assert result.unpinned == 3


def test_environment_markers_do_not_break_pins(make_dir):
    repo = _repo(make_dir, {"requirements.txt": 'tomli==2.0.1; python_version < "3.11"\n'})
    (dep,) = plague(repo, offline=True).dependencies
    assert dep.pinned and dep.version == "2.0.1"


def test_the_oracle_answers_through_the_fake_wire(make_dir):
    repo = _repo(make_dir, {"requirements.txt": "flask==0.5\nsafe-lib==1.0\n"})
    asked: list[dict] = []

    def fake_batch(queries):
        asked.extend(queries)
        return [["GHSA-xxxx-yyyy"], []]  # flask afflicted, safe-lib clean

    result = plague(repo, query_batch=fake_batch, vuln_summary=lambda vid: f"summary of {vid}")
    assert result.checked
    assert [q["package"]["name"] for q in asked] == ["flask", "safe-lib"]
    (affliction,) = result.afflictions
    assert affliction.id == "GHSA-xxxx-yyyy"
    assert affliction.package == "flask" and affliction.version == "0.5"
    assert affliction.summary == "summary of GHSA-xxxx-yyyy"


def test_unpinned_dependencies_are_never_queried(make_dir):
    repo = _repo(make_dir, {"requirements.txt": "django>=4\n"})
    result = plague(repo, query_batch=lambda q: [[] for _ in q], vuln_summary=lambda v: "")
    assert result.unpinned == 1 and result.afflictions == []


def test_render_says_when_the_oracle_was_skipped(make_dir):
    repo = _repo(make_dir, {"requirements.txt": "flask==3.0.0\n"})
    text = render_plague(plague(repo, offline=True))
    assert "oracle was not consulted" in text and "flask" in text
