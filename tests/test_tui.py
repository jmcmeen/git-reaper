"""The Sanctum: Pilot tests for the Textual TUI's chambers.

Runs only with the ``git-reaper[tui]`` extra. Driven through asyncio.run so we
need no pytest-asyncio. Thread workers are awaited with wait_for_complete --
pilot.pause() alone does not wait for a thread to finish.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, Input, Label, OptionList, Select, Static, TextArea

from git_reaper import config
from git_reaper.tui import (
    CHAMBERS,
    AltarScreen,
    BrowseScreen,
    ConsoleScreen,
    CryptMapScreen,
    GrimoireScreen,
    HelpScreen,
    NecropolisScreen,
    ReaperApp,
    ReliquaryScreen,
    SaveScreen,
    SeanceScreen,
)
from git_reaper.tui_ops import OPERATIONS

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


async def _enter(app: ReaperApp, pilot, name: str):
    """Walk from wherever we are into a chamber; return its screen."""
    app.goto_chamber(name)
    await pilot.pause()
    return app.screen


def _op_ids(altar: AltarScreen) -> set[str]:
    ops = altar.query_one("#operations", OptionList)
    ids = set()
    for i in range(ops.option_count):
        oid = ops.get_option_at_index(i).id
        if oid is not None:  # skip group headers
            ids.add(oid)
    return ids


# -- the sanctum: crypt map and navigation ------------------------------------


def test_boots_on_the_crypt_map_in_dracula(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            assert app.theme == "reaper-dracula"
            assert "reaper-dracula" in app.available_themes
            assert isinstance(app.screen, CryptMapScreen)
            doors = app.screen.query_one("#doors", OptionList)
            assert doors.option_count == len(CHAMBERS)

    asyncio.run(scenario())


def test_every_door_opens_and_escape_returns(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            expected = {
                "altar": AltarScreen,
                "grimoire": GrimoireScreen,
                "console": ConsoleScreen,
                "necropolis": NecropolisScreen,
                "reliquary": ReliquaryScreen,
                "seance": SeanceScreen,
            }
            for name, cls in expected.items():
                screen = await _enter(app, pilot, name)
                assert isinstance(screen, cls), name
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, CryptMapScreen)

    asyncio.run(scenario())


def test_number_keys_jump_between_chambers(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            # the number bindings work but stay out of the footer, which
            # would otherwise wrap on binding-heavy chambers
            assert all(binding.show is False for binding in ReaperApp.BINDINGS)
            await pilot.press("2")
            await pilot.pause()
            assert isinstance(app.screen, GrimoireScreen)
            await pilot.press("5")
            await pilot.pause()
            assert isinstance(app.screen, ReliquaryScreen)

    asyncio.run(scenario())


def test_chambers_keep_state_between_visits(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            artifact = altar.query_one("#preview", TextArea).text
            assert artifact
            await _enter(app, pilot, "seance")
            revisit = await _enter(app, pilot, "altar")
            assert revisit is altar  # same screen instance, state intact
            assert revisit.query_one("#preview", TextArea).text == artifact

    asyncio.run(scenario())


def test_altar_reaps_a_positional_ritual(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.set_operation("autopsy")
            if altar._options_ready is not None:
                await altar._options_ready
            altar.query_one("#opt-path", Input).value = "README.md"
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            text = altar.query_one("#preview", TextArea).text
            assert "schema:    autopsy/v1" in text
            # an empty path surfaces the runner's plain error, not a crash
            altar.query_one("#opt-path", Input).value = ""
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            status = str(altar.query_one("#status", Label).render())
            assert "autopsy needs a file" in status

    asyncio.run(scenario())


# -- the altar -----------------------------------------------------------------


def test_altar_lists_every_ritual(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            assert _op_ids(altar) == {op.key for op in OPERATIONS}

    asyncio.run(scenario())


def test_reap_populates_preview(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_reap()  # default ritual is 'limbs'
            await app.workers.wait_for_complete()
            await pilot.pause()
            preview = altar.query_one("#preview", TextArea).text
            assert preview.startswith("```") and "directories," in preview

    asyncio.run(scenario())


def test_arrow_keys_select_without_enter(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            ops = altar.query_one("#operations", OptionList)
            ops.focus()
            altar.set_operation("limbs")  # start on the first ritual
            await pilot.pause()
            await pilot.press("down")  # move highlight one ritual down; no enter
            await pilot.pause()
            assert altar.current_op.key == "harvest"  # selected on highlight
            assert altar.current_op.label in str(altar.query_one("#ritual-name").render())

    asyncio.run(scenario())


def test_descriptions_toggle_keeps_selection(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            ops = altar.query_one("#operations", OptionList)
            ops.focus()
            altar.set_operation("souls")
            await pilot.pause()

            def prompt_of(key: str) -> str:
                for i in range(ops.option_count):
                    option = ops.get_option_at_index(i)
                    if option.id == key:
                        return str(option.prompt)
                raise AssertionError(f"no option {key}")

            assert "contributors" not in prompt_of("souls")  # compact by default
            await pilot.press("d")  # roomy: descriptions beneath the names
            await pilot.pause()
            assert "contributors" in prompt_of("souls")
            assert altar.current_op.key == "souls"  # selection survives the rebuild
            await pilot.press("d")  # compact again
            await pilot.pause()
            assert "contributors" not in prompt_of("souls")
            assert altar.current_op.key == "souls"

    asyncio.run(scenario())


def test_ritual_name_and_status_are_separate_areas(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.set_operation("souls")
            await pilot.pause()
            name = str(altar.query_one("#ritual-name").render())
            assert "souls" in name  # the ritual name sits up top
            order = [c.id for c in altar.query_one("#main").children]
            assert order.index("preview") < order.index("spinner")
            assert order.index("preview") < order.index("statusbar")
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "reaped souls" in str(altar.query_one("#status").render())
            assert "souls" in str(altar.query_one("#ritual-name").render())

    asyncio.run(scenario())


def test_options_panel_rebuilds_on_ritual_change(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.set_operation("omens")
            await pilot.pause()
            assert altar.current_op.key == "omens"
            assert altar.query_one("#opt-lens", Select).value == "all"
            altar.set_operation("harvest")  # no options
            await pilot.pause()
            assert len(altar.query("#opt-lens")) == 0

    asyncio.run(scenario())


def test_format_option_changes_the_preview(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.set_operation("census")
            await pilot.pause()
            altar.query_one("#opt-format", Select).value = "json"
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert altar.query_one("#preview", TextArea).text.lstrip().startswith("{")
            assert altar._last_format == "json"

    asyncio.run(scenario())


def test_cursed_badge_shows_for_exhume(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(root))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.set_operation("exhume")
            await pilot.pause()
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert altar.query_one("#badge", Static).display is True
            assert AWS_KEY not in altar.query_one("#preview", TextArea).text  # masked

    asyncio.run(scenario())


def test_save_uses_the_current_ritual_and_format(necropolis, tmp_path):
    target = tmp_path / "out" / "limbs.md"

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            expected = altar.query_one("#preview", TextArea).text

            altar.action_save()  # opens the save modal
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
            altar = await _enter(app, pilot, "altar")
            altar.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            altar.action_browse()
            await pilot.pause()
            assert isinstance(app.screen, BrowseScreen)

    asyncio.run(scenario())


def test_source_inspector_flags_a_plain_folder(make_dir):
    folder = make_dir({"a.txt": "hi\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(folder))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "plain folder" in str(altar.query_one("#source-hint").render())

    asyncio.run(scenario())


def test_bad_source_reports_failure_without_crashing():
    async def scenario() -> None:
        app = ReaperApp(source="/no/such/crypt")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            # no artifact captured; the status names the failure, app still up
            assert altar._artifact == ""
            assert altar.query_one("#preview", TextArea).text == ""

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
            altar = await _enter(app, pilot, "altar")
            recipes = altar.query_one("#recipes", OptionList)
            assert recipes.option_count == 1
            recipes.focus()
            recipes.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert altar.query_one("#source", Input).value == "/some/where"
            assert altar.current_op.key == "census"
            # the recipe's --format json was mapped onto the options panel
            assert altar.query_one("#opt-format", Select).value == "json"

    asyncio.run(scenario())


# -- the grimoire -----------------------------------------------------------------


def test_grimoire_composes_and_inscribes_a_recipe(necropolis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            grimoire = await _enter(app, pilot, "grimoire")
            grimoire.query_one("#recipe-name", Input).value = "nightly"
            grimoire.query_one("#recipe-command", Select).value = "omens"
            await pilot.pause()
            grimoire.query_one("#recipe-source", Input).value = str(necropolis)
            grimoire.query_one("#opt-lens", Select).value = "churn"
            await pilot.pause()
            # the incantation label shows the exact CLI twin, live
            line = str(grimoire.query_one("#incantation", Label).render())
            assert "reaper omens" in line and "--lens churn" in line
            grimoire.action_save_recipe()
            await pilot.pause()
            saved = config.find_recipe("nightly", root=tmp_path)
            assert saved is not None
            assert saved.command == "omens"
            assert saved.args[0] == str(necropolis)
            assert saved.args[1:] == ["--lens", "churn"]

    asyncio.run(scenario())


def test_grimoire_loads_and_deletes_an_existing_recipe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config.save_recipe(
        config.Recipe(name="old", command="census", args=[".", "--format", "json"]),
        root=tmp_path,
    )

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            grimoire = await _enter(app, pilot, "grimoire")
            recipes = grimoire.query_one("#recipes", OptionList)
            assert recipes.option_count == 2  # (new recipe) + old
            recipes.focus()
            recipes.highlighted = 1
            await pilot.press("enter")
            await pilot.pause()
            assert grimoire.query_one("#recipe-name", Input).value == "old"
            assert grimoire.current_op.key == "census"
            assert grimoire.query_one("#opt-format", Select).value == "json"
            grimoire.action_delete_recipe()
            await pilot.pause()
            assert config.find_recipe("old", root=tmp_path) is None

    asyncio.run(scenario())


# -- the incantation console ---------------------------------------------------------


def test_console_suggests_on_slash_and_casts_a_ritual(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            box = console.query_one("#incant", Input)
            box.value = "/om"
            await pilot.pause()
            menu = console.query_one("#suggestions", OptionList)
            assert menu.display is True
            assert (menu.get_option_at_index(0).id or "") == "/omens"
            # live help names the flags for the resolving ritual
            box.value = f"census {necropolis} --format json"
            await pilot.pause()
            assert "--format" in str(console.query_one("#live-help", Static).render())
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log = console.query_one("#console-log", TextArea).text
            assert log.startswith("$ reaper census")
            assert '"total_files"' in log

    asyncio.run(scenario())


def test_console_meta_commands_and_errors(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            box = console.query_one("#incant", Input)
            box.value = "/help"
            await pilot.press("enter")
            await pilot.pause()
            assert "incantation console" in console.query_one("#console-log", TextArea).text
            box.value = "/clear"
            await pilot.press("enter")
            await pilot.pause()
            assert console.query_one("#console-log", TextArea).text == ""
            box.value = "omens --lens spooky"
            await pilot.press("enter")
            await pilot.pause()
            assert "must be one of" in console.query_one("#console-log", TextArea).text

    asyncio.run(scenario())


def test_console_history_recalls_with_up(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            box = console.query_one("#incant", Input)
            box.focus()
            box.value = "/clear"
            await pilot.press("enter")
            await pilot.pause()
            assert box.value == ""
            await pilot.press("up")
            await pilot.pause()
            assert box.value == "/clear"

    asyncio.run(scenario())


# -- the necropolis board --------------------------------------------------------------


def test_necropolis_board_reaps_the_fleet(necropolis, tmp_path, monkeypatch):
    manifest = tmp_path / "necropolis.toml"
    # a TOML literal string: Windows path backslashes are not escapes
    manifest.write_text(f"[[grave]]\nsource = '{necropolis}'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            board = await _enter(app, pilot, "necropolis")
            table = board.query_one("#graves", DataTable)
            assert table.row_count == 1  # loaded on mount from cwd
            board.action_reap_fleet()  # default ritual: census
            await app.workers.wait_for_complete()
            await pilot.pause()
            fate = table.get_cell(necropolis.name, "fate")
            assert "rest in peace" in str(fate)
            # drill in: the grave's artifact is readable in place
            board._row_selected_by_name(necropolis.name)
            preview = board.query_one("#board-preview", TextArea).text
            assert preview.startswith("<!--")

    asyncio.run(scenario())


def test_necropolis_board_gives_each_grave_its_own_crypt(make_repo, tmp_path, monkeypatch):
    # Two graves whose skills share a folder name: a shared out dir would let
    # omega's loot refresh-clobber alpha's. Each grave gets its own bundle.
    skill = "---\nname: tool\ndescription: From {0}.\n---\n{0}'s\n"
    alpha = make_repo({"skills/tool/SKILL.md": skill.format("alpha")}, name="alpha")
    omega = make_repo({"skills/tool/SKILL.md": skill.format("omega")}, name="omega")
    manifest = tmp_path / "necropolis.toml"
    manifest.write_text(
        f"[[grave]]\nsource = '{alpha}'\n\n[[grave]]\nsource = '{omega}'\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            board = await _enter(app, pilot, "necropolis")
            board.query_one("#fleet-ritual", Select).value = "scavenge"
            board.action_reap_fleet()
            await app.workers.wait_for_complete()
            await pilot.pause()
            crypt = tmp_path / "skill-crypt"
            alpha_loot = (crypt / "alpha/tool/SKILL.md").read_text(encoding="utf-8")
            omega_loot = (crypt / "omega/tool/SKILL.md").read_text(encoding="utf-8")
            assert alpha_loot.endswith("alpha's\n") and omega_loot.endswith("omega's\n")
            table = board.query_one("#graves", DataTable)
            assert "1 skills interred" in str(table.get_cell("alpha", "summary"))

    asyncio.run(scenario())


# -- the reliquary ------------------------------------------------------------------


def test_reliquary_triages_and_badges_a_cursed_repo(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(root))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            reliquary = await _enter(app, pilot, "reliquary")
            reliquary.action_triage()
            await app.workers.wait_for_complete()
            await pilot.pause()
            slab = reliquary.query_one("#slab", DataTable)
            assert slab.row_count > 0
            assert reliquary.query_one("#badge", Static).display is True
            # the raw secret never reaches the slab
            for i in range(slab.row_count):
                assert AWS_KEY not in " ".join(str(c) for c in slab.get_row_at(i))

    asyncio.run(scenario())


# -- the seance table ----------------------------------------------------------------


def test_seance_heatmap_filters_commits_by_hour(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            seance = await _enter(app, pilot, "seance")
            await app.workers.wait_for_complete()
            await pilot.pause()
            heatmap = seance.query_one("#heatmap", DataTable)
            assert heatmap.row_count == 7  # Mon..Sun
            commits = seance.query_one("#hour-commits", DataTable)
            total = commits.row_count
            assert total > 0
            # the fixture's commits land at 02:00; filter to that hour
            seance._filter_hour(3, 2)  # Thu 02:00
            await pilot.pause()
            assert 0 < seance.query_one("#hour-commits", DataTable).row_count <= total

    asyncio.run(scenario())


def test_seance_scries_two_refs(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            seance = await _enter(app, pilot, "seance")
            await app.workers.wait_for_complete()
            await pilot.pause()
            seance.query_one("#ref-a", Input).value = "v1.0.0"
            seance.query_one("#ref-b", Input).value = "HEAD"
            seance.action_scry()
            await app.workers.wait_for_complete()
            await pilot.pause()
            preview = seance.query_one("#board-preview", TextArea).text
            assert "v1.0.0 .. HEAD" in preview

    asyncio.run(scenario())
