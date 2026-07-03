"""Ward: the composite CI gate and its [ward] grimoire table."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from git_reaper import config
from git_reaper.cli import app
from git_reaper.core import ward as ward_core
from git_reaper.models import RepoRef

runner = CliRunner()

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"

#: "now" pinned to 2020-03-01T00:00:00Z, after every scripted commit.
NOW = 1583020800.0


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


# -- the [ward] table ---------------------------------------------------------


def test_ward_policy_defaults_to_exhume_any(tmp_path):
    policy, source = config.ward_policy(tmp_path)
    assert policy == {"exhume": "any"}
    assert source == "default"


def test_ward_policy_reads_the_grimoire(tmp_path):
    (tmp_path / ".reaperrc").write_text(
        '[ward]\nexhume = "high"\nomens = 0.8\nrot = "365d"\nskills = ["skills/x"]\n',
        encoding="utf-8",
    )
    policy, source = config.ward_policy(tmp_path)
    assert policy == {"exhume": "high", "omens": 0.8, "rot": "365d", "skills": ["skills/x"]}
    assert source == ".reaperrc"


def test_ward_policy_rejects_miswritten_tables(tmp_path):
    (tmp_path / ".reaperrc").write_text("[ward]\nhexes = 3\n", encoding="utf-8")
    with pytest.raises(config.GrimoireError, match="unknown ward key"):
        config.ward_policy(tmp_path)
    (tmp_path / ".reaperrc").write_text("[ward]\nomens = 2\n", encoding="utf-8")
    with pytest.raises(config.GrimoireError, match="between 0 and 1"):
        config.ward_policy(tmp_path)


# -- the gate itself ----------------------------------------------------------


def test_ward_holds_on_a_clean_repo(make_repo):
    root = make_repo({"README.md": "nothing buried here\n"})
    result = ward_core.ward(ref(root), {"exhume": "any"}, now=NOW)
    assert [c.name for c in result.checks] == ["exhume"]
    assert result.checks[0].ok
    assert not result.cursed


def test_ward_breaks_on_a_leaky_repo(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})
    result = ward_core.ward(ref(root), {"exhume": "any"}, now=NOW)
    assert result.cursed
    assert AWS_KEY not in result.checks[0].detail  # masked, always


def test_ward_rot_threshold(make_history):
    root = make_history(
        [{"message": "old", "when": "2019-01-01T00:00:00+00:00", "write": {"old.md": "x\n"}}],
        name="rotten",
    )
    fresh = ward_core.ward(ref(root), {"exhume": "off", "rot": "3650d"}, now=NOW)
    assert not fresh.cursed
    rotten = ward_core.ward(ref(root), {"exhume": "off", "rot": "30d"}, now=NOW)
    assert rotten.cursed
    assert rotten.checks[0].name == "rot" and rotten.checks[0].findings == 1


def test_ward_omens_threshold(necropolis):
    lax = ward_core.ward(ref(necropolis), {"exhume": "off", "omens": 1.0}, now=NOW)
    assert not lax.cursed
    paranoid = ward_core.ward(ref(necropolis), {"exhume": "off", "omens": 0.0}, now=NOW)
    assert paranoid.cursed  # every file scores at least 0.0


def test_ward_skill_freshness(make_repo, tmp_path):
    root = make_repo({"a.md": "hi\n"})
    skill = tmp_path / "skills" / "corpse"
    skill.mkdir(parents=True)
    stale_stamp = f"<!--\nsource:    {root}\nsha:       0000000deadbeef\nprofile:   repo\n-->\n"
    (skill / "SKILL.md").write_text(stale_stamp, encoding="utf-8")
    result = ward_core.ward(ref(root), {"exhume": "off", "skills": [str(skill)]}, now=NOW)
    assert result.cursed
    assert "stale" in result.checks[0].detail


def test_a_crashed_ward_fails_closed(make_repo):
    root = make_repo({"a.md": "hi\n"})
    result = ward_core.ward(ref(root), {"exhume": "off", "rot": "eleventy"}, now=NOW)
    assert result.cursed
    assert "the check itself failed" in result.checks[0].detail


def test_ward_cli_exit_codes(make_repo, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no [ward] table: the default policy gates secrets
    clean = make_repo({"README.md": "rest easy\n"}, name="clean")
    ok = runner.invoke(app, ["--plain", "ward", str(clean)])
    assert ok.exit_code == 0
    assert "schema:    ward/v1" in ok.stdout

    leaky = make_repo({"leak.env": f"KEY={AWS_KEY}\n"}, name="leaky")
    cursed = runner.invoke(app, ["--plain", "ward", str(leaky)])
    assert cursed.exit_code == 3
    assert AWS_KEY not in cursed.output
