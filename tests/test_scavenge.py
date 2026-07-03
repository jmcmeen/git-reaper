"""Scavenging: existing skill folders lifted whole into a library."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from git_reaper import tui_ops
from git_reaper.cli import app
from git_reaper.core import fleet
from git_reaper.core import scavenge as scavenge_core
from git_reaper.core.source import resolve_source

runner = CliRunner()

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(64))

SKILLED = {
    "README.md": "# corpse\n",
    "skills/alpha/SKILL.md": (
        '---\nname: alpha\ndescription: "Teaches alpha | with a pipe."\n---\n\n# alpha\n'
    ),
    "skills/alpha/reference/notes.md": "notes\n",
    "skills/alpha/assets/icon.png": PNG_BYTES,
    "docs/beta/SKILL.md": "---\nname: beta\ndescription: Teaches beta.\n---\n",
    "src/main.py": "print('not a skill')\n",
}


def _scavenge(root: Path, out: Path, excludes: list[str] | None = None):
    resolved = resolve_source(str(root))
    return scavenge_core.scavenge(
        resolved.repo, out, excludes=excludes, generated="2026-01-01T00:00:00Z"
    )


def test_scavenge_lifts_skill_folders_whole(make_repo, tmp_path):
    root = make_repo(SKILLED)
    out = tmp_path / "crypt"
    result = _scavenge(root, out)

    assert [(s.name, s.path) for s in result.skills] == [
        ("beta", "docs/beta"),
        ("alpha", "skills/alpha"),
    ]
    # The folder travels whole: prose, references, and binary assets byte-for-byte.
    assert (out / "alpha/reference/notes.md").read_text(encoding="utf-8") == "notes\n"
    assert (out / "alpha/assets/icon.png").read_bytes() == PNG_BYTES
    alpha = next(s for s in result.skills if s.name == "alpha")
    assert alpha.files == 3
    # The description came from the skill's own frontmatter, pipes escaped.
    assert alpha.description == "Teaches alpha \\| with a pipe."


def test_routing_index_lists_the_loot(make_repo, tmp_path):
    root = make_repo(SKILLED)
    out = tmp_path / "crypt"
    result = _scavenge(root, out)

    index = (out / "SKILL.md").read_text(encoding="utf-8")
    assert index.startswith("---\nname: crypt\n")
    assert "2 skills scavenged" in index
    assert "| [alpha](alpha/SKILL.md) | skills/alpha | Teaches alpha \\| with a pipe. |" in index
    assert "| [beta](beta/SKILL.md) | docs/beta | Teaches beta. |" in index
    assert result.provenance.schema == "scavenge/v1"


def test_topmost_skill_wins(make_repo, tmp_path):
    root = make_repo(
        {
            "pack/SKILL.md": "---\nname: pack\n---\n",
            "pack/nested/SKILL.md": "---\nname: nested\n---\n",
        }
    )
    result = _scavenge(root, tmp_path / "crypt")
    # One skill, taken whole; the nested SKILL.md rides along inside it.
    assert [s.path for s in result.skills] == ["pack"]
    assert (tmp_path / "crypt/pack/nested/SKILL.md").is_file()


def test_same_name_skills_are_numbered(make_repo, tmp_path):
    root = make_repo(
        {
            "a/tool/SKILL.md": "---\nname: tool\n---\n",
            "b/tool/SKILL.md": "---\nname: tool\n---\n",
        }
    )
    result = _scavenge(root, tmp_path / "crypt")
    assert [s.name for s in result.skills] == ["tool", "tool-2"]
    assert (tmp_path / "crypt/tool-2/SKILL.md").is_file()


def test_ignore_rules_hold(make_repo, tmp_path):
    root = make_repo(
        {
            ".gitignore": "junk/\nhidden/\n",
            "skills/alpha/SKILL.md": "---\nname: alpha\n---\n",
            "skills/alpha/junk/cache.bin": "cached\n",
            "hidden/SKILL.md": "---\nname: hidden\n---\n",
        }
    )
    result = _scavenge(root, tmp_path / "crypt")
    # The ignored skill folder is never found; ignored files inside a taken
    # skill folder stay buried.
    assert [s.path for s in result.skills] == ["skills/alpha"]
    assert not (tmp_path / "crypt/alpha/junk").exists()


def test_root_skill_takes_the_source_name(make_repo, tmp_path):
    root = make_repo(
        {
            "SKILL.md": "---\nname: corpse\ndescription: The repo is the skill.\n---\n",
            "reference/notes.md": "notes\n",
        }
    )
    result = _scavenge(root, tmp_path / "crypt")
    assert [(s.name, s.path) for s in result.skills] == [("corpse", ".")]
    assert (tmp_path / "crypt/corpse/reference/notes.md").is_file()
    # The grave's own plumbing never travels.
    assert not (tmp_path / "crypt/corpse/.git").exists()


def test_rescavenge_refreshes_instead_of_numbering(make_repo, tmp_path):
    root = make_repo(SKILLED)
    out = tmp_path / "crypt"
    _scavenge(root, out)
    (root / "skills/alpha/reference/notes.md").write_text("edited\n", encoding="utf-8")
    result = _scavenge(root, out)

    assert [s.name for s in result.skills] == ["beta", "alpha"]
    assert not (out / "alpha-2").exists()
    assert (out / "alpha/reference/notes.md").read_text(encoding="utf-8") == "edited\n"


def test_nothing_found_writes_nothing(make_repo, tmp_path):
    root = make_repo({"README.md": "no skills here\n"})
    out = tmp_path / "crypt"
    result = _scavenge(root, out)
    assert result.skills == []
    assert not out.exists()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_symlinks_stay_buried(make_repo, tmp_path):
    root = make_repo({"skills/alpha/SKILL.md": "---\nname: alpha\n---\n"})
    (root / "skills/alpha/escape").symlink_to(root / "README.md")
    _scavenge(root, tmp_path / "crypt")
    assert not (tmp_path / "crypt/alpha/escape").exists()


def test_cli_scavenge_json_round_trip(make_repo, tmp_path):
    root = make_repo(SKILLED)
    out = tmp_path / "crypt"
    result = runner.invoke(
        app, ["--plain", "scavenge", str(root), "--out", str(out), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["provenance"]["schema"] == "scavenge/v1"
    assert {s["name"] for s in data["skills"]} == {"alpha", "beta"}


def test_cli_empty_graves_still_rest_in_peace(make_repo, tmp_path):
    root = make_repo({"README.md": "bare\n"})
    result = runner.invoke(app, ["--plain", "scavenge", str(root), "--out", str(tmp_path / "c")])
    assert result.exit_code == 0, result.output


def test_tui_operation_scavenges_and_shows_the_loot(make_repo, tmp_path):
    root = make_repo(SKILLED)
    op = tui_ops.OPERATIONS_BY_KEY["scavenge"]
    out = tmp_path / "crypt"
    opts = op.defaults() | {"out": str(out)}
    result = op.run(resolve_source(str(root)).repo, opts)
    # The reap really wrote the library, and the preview is its routing index.
    assert (out / "alpha/SKILL.md").is_file()
    assert "| [alpha](alpha/SKILL.md) | skills/alpha |" in result.text
    assert result.summary == f"2 skills interred in {out}"
    assert not result.cursed


def test_tui_operation_reports_empty_graves(make_repo, tmp_path):
    root = make_repo({"README.md": "bare\n"})
    op = tui_ops.OPERATIONS_BY_KEY["scavenge"]
    opts = op.defaults() | {"out": str(tmp_path / "crypt")}
    result = op.run(resolve_source(str(root)).repo, opts)
    assert result.summary == "the graves were empty"
    assert not (tmp_path / "crypt").exists()


def test_tui_incantation_twin_stays_castable():
    # The console line the TUI shows must be the real CLI grammar: the out
    # flag appears only when it strays from the CLI's own default.
    op = tui_ops.OPERATIONS_BY_KEY["scavenge"]
    assert tui_ops.incantation_args(op, op.defaults()) == []
    assert tui_ops.incantation_args(op, op.defaults() | {"out": "crypt"}) == ["--out", "crypt"]


def test_fleet_treats_scavenge_as_a_bundle(tmp_path):
    graves = [
        fleet.Grave(name="alpha", source="/graves/alpha"),
        fleet.Grave(name="omega", source="/graves/omega"),
    ]
    out_dir = tmp_path / "crypt"

    def fake_runner(argv: list[str]) -> int:
        assert argv[0] == "scavenge"
        target = Path(argv[argv.index("--out") + 1])
        if target.name == "omega":
            return 1
        (target / "loot").mkdir(parents=True)
        (target / "SKILL.md").write_text(
            f'---\nname: {target.name}\ndescription: "Loot from {target.name}."\n---\n',
            encoding="utf-8",
        )
        return 0

    result = fleet.necropolis("scavenge", [], graves, out_dir, fake_runner)
    assert result.graves[0].artifact == str(out_dir / "alpha")
    # The fleet index skill reads each crypt's routing description back.
    index_skill = (out_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "| [alpha](alpha/SKILL.md) | /graves/alpha | Loot from alpha. |" in index_skill
    assert "Not harvested" in index_skill and "omega" in index_skill
