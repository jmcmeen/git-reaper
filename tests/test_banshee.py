"""Banshee: the polling watcher and its scream."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from git_reaper.cli import app
from git_reaper.core import banshee as banshee_core

runner = CliRunner()


def test_snapshot_and_changed_detect_every_kind_of_change(tmp_path):
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two\n", encoding="utf-8")
    before = banshee_core.snapshot(tmp_path)
    assert set(before) == {"a.txt", "b.txt"}

    (tmp_path / "a.txt").write_text("one, grown\n", encoding="utf-8")  # modified
    (tmp_path / "b.txt").unlink()  # deleted
    (tmp_path / "c.txt").write_text("new\n", encoding="utf-8")  # added
    after = banshee_core.snapshot(tmp_path)
    assert banshee_core.changed(before, after) == ["a.txt", "b.txt", "c.txt"]
    assert banshee_core.changed(after, after) == []


def test_snapshot_honors_ignore_rules(tmp_path):
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (tmp_path / "noise.log").write_text("zzz\n", encoding="utf-8")
    (tmp_path / "kept.md").write_text("k\n", encoding="utf-8")
    assert set(banshee_core.snapshot(tmp_path)) == {".gitignore", "kept.md"}


def test_haunt_screams_on_change_and_counts(tmp_path):
    (tmp_path / "watched.txt").write_text("v1\n", encoding="utf-8")
    heard: list[list[str]] = []
    polls = iter(range(10))

    def fake_sleep(_seconds: float) -> None:
        # mutate on the second poll only; the clock never actually ticks
        if next(polls) == 1:
            (tmp_path / "watched.txt").write_text("v2\n", encoding="utf-8")

    screams = banshee_core.haunt(
        tmp_path, heard.append, interval=0.01, max_polls=4, sleep=fake_sleep
    )
    assert screams == 1
    assert heard == [["watched.txt"]]


def test_haunt_once_stops_after_the_first_scream(tmp_path):
    (tmp_path / "w.txt").write_text("v1\n", encoding="utf-8")
    count = 0

    def restless_sleep(_seconds: float) -> None:
        nonlocal count
        count += 1
        (tmp_path / "w.txt").write_text(f"v{count}\n", encoding="utf-8")

    screams = banshee_core.haunt(
        tmp_path, lambda _c: None, once=True, max_polls=10, sleep=restless_sleep
    )
    assert screams == 1
    assert count == 1  # stopped right after the first scream


def test_banshee_cli_runs_the_recipe_and_watches(make_repo, tmp_path, monkeypatch):
    root = make_repo({"README.md": "# hi\n"})
    monkeypatch.chdir(tmp_path)
    Path(".reaperrc").write_text(
        f'[recipes.count]\ncommand = "census"\nargs = ["{root.as_posix()}"]\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "--plain",
            "banshee",
            "count",
            "--source",
            str(root),
            "--max-polls",
            "1",
            "--interval",
            "0.01",
        ],
    )
    assert result.exit_code == 0
    assert "schema:    census/v1" in result.stdout  # the initial cast ran
    assert "the banshee watches" in result.output


def test_banshee_cli_refuses_nonsense(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    unknown = runner.invoke(app, ["--plain", "banshee", "nope"])
    assert unknown.exit_code == 1

    Path(".reaperrc").write_text(
        '[recipes.loop]\ncommand = "cast"\nargs = ["loop"]\n', encoding="utf-8"
    )
    recursive = runner.invoke(app, ["--plain", "banshee", "loop"])
    assert recursive.exit_code == 1
    assert "recursion" in recursive.output
