"""The Summoning: Pilot smoke tests for the Textual TUI.

Runs only with the ``git-reaper[tui]`` extra. Driven through asyncio.run so we
need no pytest-asyncio. Thread workers are awaited with wait_for_complete --
pilot.pause() alone does not wait for a thread to finish.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import Input, OptionList, Select, Static, TextArea

from git_reaper.tui import BrowseScreen, HelpScreen, ReaperApp, SaveScreen
from git_reaper.tui_ops import OPERATIONS

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


def _op_ids(app: ReaperApp) -> set[str]:
    ops = app.query_one("#operations", OptionList)
    ids = set()
    for i in range(ops.option_count):
        oid = ops.get_option_at_index(i).id
        if oid is not None:  # skip group headers
            ids.add(oid)
    return ids


def test_boots_dracula_with_every_ritual(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            assert app.theme == "reaper-dracula"
            assert "reaper-dracula" in app.available_themes
            assert _op_ids(app) == {op.key for op in OPERATIONS}

    asyncio.run(scenario())


def test_reap_populates_preview(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.action_reap()  # default ritual is 'limbs'
            await app.workers.wait_for_complete()
            await pilot.pause()
            preview = app.query_one("#preview", TextArea).text
            assert preview.startswith("```") and "directories," in preview

    asyncio.run(scenario())


def test_arrow_keys_select_without_enter(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            ops = app.query_one("#operations", OptionList)
            ops.focus()
            app.set_operation("limbs")  # start on the first ritual
            await pilot.pause()
            await pilot.press("down")  # move highlight one ritual down; no enter
            await pilot.pause()
            assert app.current_op.key == "harvest"  # the next ritual, selected on highlight
            # the top ritual-name area tracks the highlight
            assert app.current_op.label in str(app.query_one("#ritual-name").render())

    asyncio.run(scenario())


def test_ritual_name_and_status_are_separate_areas(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.set_operation("souls")
            await pilot.pause()
            name = str(app.query_one("#ritual-name").render())
            assert "souls" in name  # the ritual name sits up top
            order = [c.id for c in app.query_one("#main").children]
            assert order.index("preview") < order.index("spinner")
            assert order.index("preview") < order.index("statusbar")
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            # the bottom status carries the run summary; the top still names the ritual
            assert "reaped souls" in str(app.query_one("#status").render())
            assert "souls" in str(app.query_one("#ritual-name").render())

    asyncio.run(scenario())


def test_options_panel_rebuilds_on_ritual_change(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.set_operation("omens")
            await pilot.pause()
            assert app.current_op.key == "omens"
            assert app.query_one("#opt-lens", Select).value == "all"
            app.set_operation("harvest")  # no options
            await pilot.pause()
            assert len(app.query("#opt-lens")) == 0

    asyncio.run(scenario())


def test_format_option_changes_the_preview(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.set_operation("census")
            await pilot.pause()
            app.query_one("#opt-format", Select).value = "json"
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#preview", TextArea).text.lstrip().startswith("{")
            assert app._last_format == "json"

    asyncio.run(scenario())


def test_cursed_badge_shows_for_exhume(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(root))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.set_operation("exhume")
            await pilot.pause()
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one("#badge", Static).display is True
            assert AWS_KEY not in app.query_one("#preview", TextArea).text  # masked

    asyncio.run(scenario())


def test_save_uses_the_current_ritual_and_format(necropolis, tmp_path):
    target = tmp_path / "out" / "limbs.md"

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            expected = app.query_one("#preview", TextArea).text

            app.action_save()  # opens the save modal
            await pilot.pause()
            assert isinstance(app.screen, SaveScreen)
            assert app.screen.query_one("#path", Input).value == "limbs.md"
            app.screen.query_one("#path", Input).value = str(target)
            await pilot.click("#ok")
            await pilot.pause()
            assert target.read_text() == expected

    asyncio.run(scenario())


def test_help_and_browse_modals_open(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            app.action_browse()
            await pilot.pause()
            assert isinstance(app.screen, BrowseScreen)

    asyncio.run(scenario())


def test_source_inspector_flags_a_plain_folder(make_dir):
    folder = make_dir({"a.txt": "hi\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(folder))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "plain folder" in str(app.query_one("#source-hint").render())

    asyncio.run(scenario())


def test_bad_source_reports_failure_without_crashing():
    async def scenario() -> None:
        app = ReaperApp(source="/no/such/crypt")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            app.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            # no artifact captured; the status names the failure, app still up
            assert app._artifact == ""
            assert app.query_one("#preview", TextArea).text == ""

    asyncio.run(scenario())


def test_recipe_prefills_source_and_ritual(tmp_path, monkeypatch):
    # A .reaperrc with one recipe; selecting it prefills the source + ritual.
    rc = tmp_path / ".reaperrc"
    rc.write_text(
        "[recipes.nightly]\ncommand = 'census'\nargs = ['/some/where', '--format', 'json']\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            recipes = app.query_one("#recipes", OptionList)
            assert recipes.option_count == 1
            recipes.focus()
            recipes.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#source", Input).value == "/some/where"
            assert app.current_op.key == "census"
            # the recipe's --format json was mapped onto the options panel
            assert app.query_one("#opt-format", Select).value == "json"

    asyncio.run(scenario())
