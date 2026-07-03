"""Revenant: resurrections and repeat offenders."""

from __future__ import annotations

from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import revenant as revenant_core
from git_reaper.models import RepoRef

runner = CliRunner()


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


RESURRECTION = [
    {
        "message": "birth",
        "when": "2020-01-01T00:00:00+00:00",
        "write": {"cursed.py": "v1\n", "calm.py": "ok\n"},
    },
    {"message": "death", "when": "2020-01-02T00:00:00+00:00", "delete": ["cursed.py"]},
    {
        "message": "it returns",
        "when": "2020-01-03T00:00:00+00:00",
        "write": {"cursed.py": "v2\n"},
    },
    {"message": "death again", "when": "2020-01-04T00:00:00+00:00", "delete": ["cursed.py"]},
]


def test_revenant_counts_deaths_and_rebirths(make_history):
    root = make_history(RESURRECTION)
    result = revenant_core.revenant(ref(root))
    assert len(result.revenants) == 1
    risen = result.revenants[0]
    assert risen.path == "cursed.py"
    assert risen.deaths == 2
    assert risen.rebirths == 1
    assert not risen.alive  # died again at the end
    assert risen.last_died.startswith("2020-01-04")
    assert risen.last_raised.startswith("2020-01-03")


def test_files_that_stayed_buried_are_not_revenants(make_history):
    root = make_history(RESURRECTION)
    result = revenant_core.revenant(ref(root))
    assert all(r.path != "calm.py" for r in result.revenants)


FIX_LOOP = [
    {"message": "seed", "when": "2020-01-01T00:00:00+00:00", "write": {"flaky.py": "v1\n"}},
    {
        "message": "fix the crash",
        "when": "2020-01-02T00:00:00+00:00",
        "write": {"flaky.py": "v2\n"},
    },
    {
        "message": "fix it harder",
        "when": "2020-01-03T00:00:00+00:00",
        "write": {"flaky.py": "v3\n"},
    },
    {
        "message": "fix the fix",
        "when": "2020-01-04T00:00:00+00:00",
        "write": {"flaky.py": "v4\n"},
    },
]


def test_repeat_offenders_need_min_fixes(make_history):
    root = make_history(FIX_LOOP)
    result = revenant_core.revenant(ref(root))
    assert [o.path for o in result.offenders] == ["flaky.py"]
    offender = result.offenders[0]
    assert offender.bug_commits == 3
    assert offender.last_fix.startswith("2020-01-04")

    stricter = revenant_core.revenant(ref(root), min_fixes=4)
    assert stricter.offenders == []


def test_dead_files_cannot_offend(make_history):
    script = [
        *FIX_LOOP,
        {"message": "gone", "when": "2020-01-05T00:00:00+00:00", "delete": ["flaky.py"]},
    ]
    root = make_history(script, name="deadoffender")
    result = revenant_core.revenant(ref(root))
    assert result.offenders == []


def test_revenant_cli(make_history):
    root = make_history(RESURRECTION)
    result = runner.invoke(app, ["--plain", "revenant", str(root)])
    assert result.exit_code == 0
    assert "schema:    revenant/v1" in result.stdout
    assert "cursed.py" in result.stdout
    assert "dead again" in result.stdout
