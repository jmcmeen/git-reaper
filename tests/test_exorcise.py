"""Exorcise: the purge plan that never swings the stake itself."""

from __future__ import annotations

from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import exorcise as exorcise_core
from git_reaper.models import RepoRef

runner = CliRunner()

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"
BIG = "x" * 4096  # a "huge" blob once min_size drops to 1KB


def ref(root) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


HAUNTED = [
    {
        "message": "bury the bodies",
        "when": "2020-01-01T00:00:00+00:00",
        "write": {"assets/huge.bin": BIG, "config/leak.env": f"KEY={AWS_KEY}\n"},
    },
    {
        "message": "hide the evidence",
        "when": "2020-01-02T00:00:00+00:00",
        "delete": ["assets/huge.bin", "config/leak.env"],
        "write": {"README.md": "clean now\n"},
    },
]


def test_exorcise_plans_for_blobs_and_secrets(make_history):
    root = make_history(HAUNTED)
    result = exorcise_core.exorcise(ref(root), min_size=1024)
    reasons = {t.path: t.reason for t in result.targets}
    assert "assets/huge.bin" in reasons and reasons["assets/huge.bin"].startswith("dead blob")
    assert reasons.get("config/leak.env", "").startswith("secret:")
    assert AWS_KEY not in "\n".join(f"{t.path} {t.reason}" for t in result.targets)

    joined = "\n".join(result.commands)
    assert "git filter-repo --invert-paths" in joined
    assert "--path assets/huge.bin" in joined
    assert "--strip-blobs-bigger-than 1K" in joined
    assert "bfg " in joined
    assert result.warnings  # never a plan without the sermon


def test_exorcise_can_skip_the_secret_pass(make_history):
    root = make_history(HAUNTED)
    result = exorcise_core.exorcise(ref(root), min_size=1024, secrets=False)
    assert all(not t.reason.startswith("secret:") for t in result.targets)


def test_exorcise_on_a_clean_repo_plans_nothing(make_repo):
    root = make_repo({"README.md": "nothing to hide\n"})
    result = exorcise_core.exorcise(ref(root))
    assert result.targets == []
    assert result.commands == []
    assert result.warnings == []


def test_exorcise_cli_prints_but_never_performs(make_history):
    root = make_history(HAUNTED)
    before = {p.name for p in root.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["--plain", "exorcise", str(root), "--min-size", "1KB"])
    assert result.exit_code == 0
    assert "schema:    exorcise/v1" in result.stdout
    assert "nothing above was executed" in result.stdout
    after = {p.name for p in root.rglob("*") if p.is_file()}
    assert before == after  # the plan touched nothing
