"""The Summoning: Pilot smoke tests for the Textual TUI.

Runs only with the ``git-reaper[tui]`` extra. Driven through asyncio.run so we
need no pytest-asyncio. Thread workers are awaited with wait_for_complete --
pilot.pause() alone does not wait for a thread to finish.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import Input, OptionList, TextArea

from git_reaper.tui import ReaperApp, SaveScreen, SplashScreen
from git_reaper.tui_ops import OPERATIONS, OPERATIONS_BY_KEY


def test_boots_and_splash_dismisses(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SplashScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert not isinstance(app.screen, SplashScreen)
            assert app.query_one("#operations", OptionList).option_count == len(OPERATIONS)

    asyncio.run(scenario())


def test_reap_populates_preview(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("enter")  # dismiss splash
            await pilot.pause()
            app.action_reap()  # default ritual is 'tree'
            await app.workers.wait_for_complete()
            await pilot.pause()
            preview = app.query_one("#preview", TextArea).text
            assert preview.startswith("```") and "directories," in preview

    asyncio.run(scenario())


def test_selecting_a_history_ritual_then_reaping(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            ops = app.query_one("#operations", OptionList)
            ops.focus()
            ops.highlighted = OPERATIONS.index(OPERATIONS_BY_KEY["chronicle"])
            await pilot.press("enter")  # select the highlighted ritual
            await pilot.pause()
            assert app.current_op.key == "chronicle"
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "schema:    chronicle/v1" in app.query_one("#preview", TextArea).text

    asyncio.run(scenario())


def test_save_writes_the_previewed_artifact(necropolis, tmp_path):
    target = tmp_path / "out" / "tree.md"

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            expected = app.query_one("#preview", TextArea).text

            app.action_save()  # opens the save modal
            await pilot.pause()
            assert isinstance(app.screen, SaveScreen)
            app.screen.query_one("#path", Input).value = str(target)
            await pilot.click("#ok")
            await pilot.pause()

            assert target.read_text() == expected

    asyncio.run(scenario())


def test_bad_source_reports_failure_without_crashing():
    async def scenario() -> None:
        app = ReaperApp(source="/no/such/crypt")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            # no artifact captured; the status names the failure, app still up
            assert app._artifact == ""
            assert app.query_one("#preview", TextArea).text == ""

    asyncio.run(scenario())


def test_recipe_prefills_source_and_ritual(necropolis, tmp_path, monkeypatch):
    # A .reaperrc with one recipe; selecting it prefills the source + ritual.
    rc = tmp_path / ".reaperrc"
    rc.write_text(
        "[recipes.nightly]\ncommand = 'census'\nargs = ['/some/where']\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.press("enter")
            await pilot.pause()
            recipes = app.query_one("#recipes", OptionList)
            assert recipes.option_count == 1
            recipes.focus()
            recipes.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#source", Input).value == "/some/where"
            assert app.current_op.key == "census"

    asyncio.run(scenario())
