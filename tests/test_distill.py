"""Skill harvesting: distill composes the rituals into a loadable skill."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import distill as distill_core
from git_reaper.core import fleet
from git_reaper.core.source import resolve_source

runner = CliRunner()


def _git(*args: str, cwd: Path) -> str:
    """Hermetic git, same discipline as the conftest fixtures."""
    env = {
        "GIT_AUTHOR_NAME": "Test Ghost",
        "GIT_AUTHOR_EMAIL": "ghost@example.com",
        "GIT_COMMITTER_NAME": "Test Ghost",
        "GIT_COMMITTER_EMAIL": "ghost@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "HOME": str(cwd),
        "PATH": "/usr/bin:/bin",
    }
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env
    )
    return proc.stdout


PYPROJECT = """
[project]
name = "crypt"
version = "0.1.0"

[project.scripts]
crypt = "crypt.cli:app"

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]
"""

MAKEFILE = """
.PHONY: test lint
test:
\tpytest
lint:
\truff check .
"""


def _history_repo(make_history) -> Path:
    return make_history(
        [
            {
                "message": "feat: raise the crypt",
                "when": "2020-01-01T00:00:00",
                "write": {
                    "pyproject.toml": PYPROJECT,
                    "Makefile": MAKEFILE,
                    "src/crypt/cli.py": "def app():\n    pass\n",
                    "tests/test_cli.py": "def test_app():\n    pass  # TODO: haunt\n",
                },
            },
            {
                "message": "fix: parser regression in cli",
                "when": "2020-02-01T00:00:00",
                "author": ("Second Ghost", "second@example.com"),
                "write": {"src/crypt/cli.py": "def app():\n    return 1\n"},
            },
            {
                "message": "fix: parser crash on empty refs",
                "when": "2020-03-01T00:00:00",
                "write": {"src/crypt/cli.py": "def app():\n    return 2\n"},
            },
        ]
    )


def _distill(root: Path, **kwargs) -> distill_core.DistillResult:
    repo = resolve_source(str(root)).repo
    return distill_core.distill(repo, generated="2026-01-01T00:00:00Z", **kwargs)


def test_distill_composes_the_rituals(make_history):
    result = _distill(_history_repo(make_history))
    assert result.name.startswith("necropolis")
    assert result.profile == "repo"
    assert result.total_files == 4
    assert "src/" in result.layout and "tests/" in result.layout
    assert "pyproject.toml" in result.tooling and "Makefile" in result.tooling
    # Commands are lifted, not guessed: pyproject tooling and Makefile targets.
    commands = {(c.kind, c.command) for c in result.commands}
    assert ("test", "pytest") in commands
    assert ("lint", "make lint") in commands
    assert ("run", "crypt") in commands
    # Commit style: all three subjects carry conventional prefixes.
    assert result.conventional_share == 1.0
    assert result.commit_prefixes == {"fix": 2, "feat": 1}
    # Gotchas: cli.py was fixed twice; the parser theme recurs.
    top = result.gotchas[0]
    assert top.path == "src/crypt/cli.py"
    assert top.bug_commits == 2
    assert result.bug_themes.get("parser") == 2
    assert result.marker_counts == {"TODO": 1}
    assert result.bus_factor >= 1
    assert result.bones is not None and result.bones.parsed_files == 2


def test_anon_reduces_owners_to_roles(make_history):
    result = _distill(_history_repo(make_history), anon=True)
    assert [s.name for s in result.owners] == ["keeper 1", "keeper 2"]
    assert all(s.email == "" for s in result.owners)
    assert sum(s.commits for s in result.owners) == 3


def test_unknown_profile_is_refused(make_history):
    with pytest.raises(ValueError, match="unknown profile"):
        _distill(_history_repo(make_history), profile="haunted")


def test_cli_writes_the_bundle_and_check_round_trips(make_history):
    root = _history_repo(make_history)
    skill = root.parent / "skills" / "necro"
    result = runner.invoke(app, ["--plain", "distill", str(root), "--out", str(skill)])
    assert result.exit_code == 0, result.output
    for rel in (
        "SKILL.md",
        "reference/structure.md",
        "reference/conventions.md",
        "reference/commands.md",
        "reference/gotchas.md",
        "reference/ownership.md",
    ):
        assert (skill / rel).is_file(), rel
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: necropolis")
    assert "git-reaper distill" in text and "profile:   repo" in text

    # Fresh: the stamped sha still matches HEAD.
    fresh = runner.invoke(app, ["--plain", "distill", "--check", str(skill)])
    assert fresh.exit_code == 0, fresh.output

    # Stale: the code moves on, the skill starts to lie, exit 3 (cursed).
    (root / "new.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "feat: move on", cwd=root)
    stale = runner.invoke(app, ["--plain", "distill", "--check", str(skill)])
    assert stale.exit_code == 3, stale.output


def test_cli_distill_zip_format(make_history, tmp_path):
    root = _history_repo(make_history)
    skill = tmp_path / "necro"
    result = runner.invoke(
        app, ["--plain", "distill", str(root), "--out", str(skill), "--format", "zip"]
    )
    assert result.exit_code == 0, result.output
    assert not skill.exists()
    archive = skill.with_name("necro.zip")
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        assert "necro/SKILL.md" in zf.namelist()


def test_write_bundle_archives_and_returns_the_archive_path(tmp_path):
    target = tmp_path / "necro"
    written = distill_core.write_bundle({"SKILL.md": "hi\n"}, target, archive="tar.gz")
    assert not target.exists()
    assert written == target.with_name("necro.tar.gz")
    assert written.is_file()


def test_check_refuses_a_directory_without_a_skill(tmp_path):
    result = runner.invoke(app, ["--plain", "distill", "--check", str(tmp_path)])
    assert result.exit_code == 1


def test_cli_refuses_an_unknown_profile(make_history):
    root = _history_repo(make_history)
    result = runner.invoke(app, ["--plain", "distill", str(root), "--profile", "haunted"])
    assert result.exit_code == 1


def test_read_stamp_recovers_source_sha_profile(make_history):
    root = _history_repo(make_history)
    skill = root.parent / "skills" / "stamped"
    runner.invoke(app, ["--plain", "distill", str(root), "--out", str(skill), "--profile", "stack"])
    stamp = distill_core.read_stamp(skill)
    assert stamp.source == str(root)
    assert stamp.profile == "stack"
    head = _git("rev-parse", "HEAD", cwd=root).strip()
    assert stamp.sha == head


def test_fleet_treats_distill_as_a_bundle(tmp_path):
    graves = [fleet.Grave(name="alpha", source="/graves/alpha")]
    out_dir = tmp_path / "skills"

    def fake_runner(argv: list[str]) -> int:
        assert argv[0] == "distill"
        target = Path(argv[argv.index("--out") + 1])
        (target / "reference").mkdir(parents=True)
        (target / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
        return 0

    result = fleet.necropolis("distill", [], graves, out_dir, fake_runner)
    outcome = result.graves[0]
    assert outcome.ok
    assert outcome.artifact == str(out_dir / "alpha")
    assert (out_dir / "alpha" / "SKILL.md").is_file()


def test_polish_pipes_prose_and_preserves_the_stamp(make_history, tmp_path):
    root = _history_repo(make_history)
    skill = root.parent / "skills" / "polished"
    polisher = tmp_path / "polish.py"
    polisher.write_text("import sys\nsys.stdout.write(sys.stdin.read().upper())\n")
    cmd = f"{sys.executable} {polisher}"
    result = runner.invoke(
        app, ["--plain", "distill", str(root), "--out", str(skill), "--polish", cmd]
    )
    assert result.exit_code == 0, result.output
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    # Frontmatter and the provenance stamp are protected from the polisher...
    assert text.startswith("---\nname: necropolis")
    assert "git-reaper distill" in text and "schema:    distill/v1" in text
    # ...while the prose below the stamp went through it.
    assert "# WORKING IN" in text
    assert (skill / "reference/gotchas.md").read_text(encoding="utf-8").count("# GOTCHAS") == 1
    # The polished skill still round-trips through --check.
    fresh = runner.invoke(app, ["--plain", "distill", "--check", str(skill)])
    assert fresh.exit_code == 0, fresh.output


def test_polish_failure_writes_nothing(make_history, tmp_path):
    root = _history_repo(make_history)
    skill = root.parent / "skills" / "unwritten"
    polisher = tmp_path / "die.py"
    polisher.write_text("import sys\nsys.stderr.write('no key\\n')\nsys.exit(9)\n")
    cmd = f"{sys.executable} {polisher}"
    result = runner.invoke(
        app, ["--plain", "distill", str(root), "--out", str(skill), "--polish", cmd]
    )
    assert result.exit_code == 1
    assert not skill.exists()


def test_polish_that_eats_the_draft_is_refused():
    with pytest.raises(distill_core.SkillError, match="returned nothing"):
        distill_core.polish_bundle(
            {"SKILL.md": "---\n---\n\n<!--\nx\n-->\nbody\n"},
            f'{sys.executable} -c "pass"',
        )


def test_fleet_distill_writes_a_routing_index_skill(tmp_path):
    graves = [
        fleet.Grave(name="alpha", source="/graves/alpha"),
        fleet.Grave(name="omega", source="/graves/omega"),
    ]
    out_dir = tmp_path / "skills"

    def fake_runner(argv: list[str]) -> int:
        target = Path(argv[argv.index("--out") + 1])
        name = target.name
        if name == "omega":
            return 1  # one grave fails; the index skill must say so
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text(
            f'---\nname: {name}\ndescription: "How to work in {name}."\n---\n',
            encoding="utf-8",
        )
        return 0

    result = fleet.necropolis("distill", [], graves, out_dir, fake_runner)
    index_skill = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    assert index_skill.startswith("---\nname: skills\n")
    assert "| [alpha](alpha/SKILL.md) | /graves/alpha | How to work in alpha. |" in index_skill
    assert "Not harvested" in index_skill and "omega" in index_skill
    assert result.index.endswith("INDEX.md")  # the plain index still exists


def test_derive_name_handles_windows_sources():
    from git_reaper.models import RepoRef

    ref = RepoRef(source="C:\\Users\\x\\necropolis", kind="local", path="C:\\Users\\x\\necropolis")
    assert distill_core.derive_name(ref) == "necropolis"
    dot = RepoRef(source=".", kind="local", path="/home/x/crypt")
    assert distill_core.derive_name(dot) == "crypt"


def test_workflow_commands_skip_ci_plumbing(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - run: pip install uv\n"
        "      - run: uv sync --dev\n"
        "      - run: uv run pytest\n",
        encoding="utf-8",
    )
    commands = distill_core._workflow_commands(workflows)
    assert [(c.kind, c.command) for c in commands] == [("test", "uv run pytest")]


def test_polish_timeout_is_a_clear_error():
    slow = f'{sys.executable} -c "import time; time.sleep(5)"'
    with pytest.raises(distill_core.SkillError, match="timed out"):
        distill_core.polish_bundle({"SKILL.md": "<!--\nx\n-->\nbody\n"}, slow, timeout=0.5)
