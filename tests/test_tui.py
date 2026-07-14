"""The Sanctum: Pilot tests for the Textual TUI's chambers.

Runs only with the ``git-reaper[tui]`` extra. Driven through asyncio.run so we
need no pytest-asyncio. Thread workers are awaited with wait_for_complete --
pilot.pause() alone does not wait for a thread to finish.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import (
    DataTable,
    DirectoryTree,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    Switch,
    TextArea,
)

from git_reaper import config
from git_reaper.tui import (
    CHAMBERS,
    AltarScreen,
    BrowseScreen,
    ConsoleScreen,
    CovenScreen,
    CryptMapScreen,
    GrimoireScreen,
    HelpScreen,
    NecropolisScreen,
    ReaperApp,
    ReliquaryScreen,
    SaveScreen,
    ScytheSpinner,
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
                "coven": CovenScreen,
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
            reliquary_key = str([name for name, *_ in CHAMBERS].index("reliquary") + 1)
            await pilot.press(reliquary_key)
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


# -- the coven ----------------------------------------------------------------------


def test_coven_composes_and_inscribes_a_rite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            coven.query_one("#rite-name", Input).value = "audit"
            coven.query_one("#step-command", Select).value = "census"
            await pilot.pause()
            await coven._add_step_button()
            coven.query_one("#step-command", Select).value = "chronicle"
            await pilot.pause()
            line = str(coven.query_one("#rite-incantation", Label).render())
            assert "reaper census '{source}'" in line
            assert "reaper chronicle '{source}'" in line
            assert "reaper perform audit ." in line
            coven.action_save_rite()
            await pilot.pause()
            saved = config.find_rite("audit", root=tmp_path)
            assert saved is not None
            assert [s.command for s in saved.steps] == ["census", "chronicle"]
            assert all("{source}" in s.args for s in saved.steps)

    asyncio.run(scenario())


def test_coven_loads_and_deletes_an_existing_rite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config.save_rite(
        config.Rite(
            name="old",
            steps=[config.RiteStep(command="census", args=["{source}", "--format", "json"])],
        ),
        root=tmp_path,
    )

    async def scenario() -> None:
        app = ReaperApp(source=".")
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            rites = coven.query_one("#rites", OptionList)
            assert rites.option_count == 2  # (new rite) + old
            rites.focus()
            rites.highlighted = 1
            await pilot.press("enter")
            await pilot.pause()
            assert coven.query_one("#rite-name", Input).value == "old"
            assert coven.current_op.key == "census"
            assert coven.query_one("#opt-format", Select).value == "json"
            coven.action_delete_rite()
            await pilot.pause()
            assert config.find_rite("old", root=tmp_path) is None

    asyncio.run(scenario())


def test_coven_runs_a_rite_across_its_steps(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            coven.query_one("#rite-name", Input).value = "quick"
            coven.query_one("#rite-sources", Input).value = str(necropolis)
            coven.query_one("#step-command", Select).value = "census"
            await pilot.pause()
            coven.action_run()
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = coven.query_one("#results", DataTable)
            assert table.row_count == 1
            assert coven._artifacts  # the drill-in preview has something to show

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


# -- the ritual list: what is selected is what is shown ------------------------


def test_altar_highlights_the_ritual_it_has_selected(necropolis):
    # index 0 is a group header, so an unhighlighted list would show limbs in
    # the options panel and the ritual name, but nowhere in the list itself.
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            ops = altar.query_one("#operations", OptionList)
            assert altar.current_op.key == OPERATIONS[0].key
            assert ops.highlighted is not None
            assert ops.get_option_at_index(ops.highlighted).id == altar.current_op.key

    asyncio.run(scenario())


# -- the modals: centred, and the browser walks both ways ----------------------


def _is_centred(screen, selector: str) -> bool:
    """The dialog sits in the middle of the modal screen, not its top-left."""
    dialog = screen.query_one(selector).region
    box = screen.region
    left, right = dialog.x, box.width - (dialog.x + dialog.width)
    top, bottom = dialog.y, box.height - (dialog.y + dialog.height)
    return abs(left - right) <= 1 and abs(top - bottom) <= 1


def test_every_modal_opens_centred(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            assert _is_centred(app.screen, "#help")
            await pilot.press("escape")
            await pilot.pause()

            altar.action_browse()
            await pilot.pause()
            assert isinstance(app.screen, BrowseScreen)
            assert _is_centred(app.screen, "#browse")
            app.screen.action_cancel()
            await pilot.pause()

            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            altar.action_save()
            await pilot.pause()
            assert isinstance(app.screen, SaveScreen)
            assert _is_centred(app.screen, "#dialog")

    asyncio.run(scenario())


def test_browse_climbs_up_out_of_a_deep_crypt(necropolis):
    deep = necropolis / "src"

    async def scenario() -> None:
        app = ReaperApp(source=str(deep))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_browse()
            await pilot.pause()
            browse = app.screen
            assert browse._root == deep.resolve()

            browse.action_up()  # the tree only walks down; the root has to move
            await pilot.pause()
            assert browse._root == necropolis.resolve()
            assert str(browse.query_one("#tree", DirectoryTree).path) == str(necropolis.resolve())
            assert browse.query_one("#browse-path", Input).value == str(necropolis.resolve())

            browse.action_choose()
            await pilot.pause()
            assert app.screen is altar
            assert altar.query_one("#source", Input).value == str(necropolis.resolve())

    asyncio.run(scenario())


def test_browse_walks_down_without_ending_the_browse(necropolis):
    # selecting a directory used to dismiss the modal on the spot, so a crypt
    # below the first level could never be reached at all.
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_browse()
            await pilot.pause()
            browse = app.screen
            tree = browse.query_one("#tree", DirectoryTree)
            tree.post_message(DirectoryTree.DirectorySelected(tree.root, necropolis / "src"))
            await pilot.pause()
            assert isinstance(app.screen, BrowseScreen)  # still browsing
            assert browse._picked == necropolis / "src"
            browse.action_choose()
            await pilot.pause()
            assert altar.query_one("#source", Input).value == str(necropolis / "src")

    asyncio.run(scenario())


def test_browse_re_roots_on_a_typed_path_and_refuses_a_bad_one(necropolis, tmp_path):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_browse()
            await pilot.pause()
            browse = app.screen
            box = browse.query_one("#browse-path", Input)

            box.value = str(tmp_path)
            await pilot.press("enter")
            await pilot.pause()
            assert browse._root == tmp_path.resolve()

            box.value = "/no/such/crypt"
            await pilot.press("enter")
            await pilot.pause()
            assert browse._root == tmp_path.resolve()  # unmoved; the modal said so

    asyncio.run(scenario())


def test_browse_opens_somewhere_sensible_for_a_vanished_source(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis / "no" / "such" / "grave"))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            altar.action_browse()
            await pilot.pause()
            assert app.screen._root == necropolis.resolve()  # the nearest real crypt
            app.screen.action_cancel()
            await pilot.pause()
            assert app.screen is altar  # cancel leaves the source alone
            assert altar.query_one("#source", Input).value == str(necropolis / "no/such/grave")

    asyncio.run(scenario())


# -- running never wedges a chamber -------------------------------------------


def test_the_coven_survives_the_same_source_twice(necropolis):
    # two rows for one source used to collide on the results table's row key;
    # the worker died mid-run, and the rite stayed "already running" forever.
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            coven.query_one("#rite-sources", Input).value = f"{necropolis}, {necropolis}"
            coven.query_one("#step-command", Select).value = "census"
            await pilot.pause()
            coven.action_run()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert coven.query_one("#results", DataTable).row_count == 2
            assert coven._rite_running is False  # the chamber is free again
            assert coven.query_one("#spinner", ScytheSpinner).display is False
            assert "performed 2/2" in str(coven.query_one("#status").render())

            coven.action_run()  # and it can be run again, which is the point
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert coven.query_one("#results", DataTable).row_count == 2

    asyncio.run(scenario())


def test_a_failed_render_still_stops_the_scythe(necropolis, monkeypatch):
    # the artifact came back fine but drawing it threw: the worker used to die
    # between the two, leaving the scythe swinging over nothing.
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")

            def _boom(*_args, **_kwargs):
                raise RuntimeError("the preview refused to draw")

            monkeypatch.setattr(altar, "_show_preview", _boom)
            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert altar.query_one("#spinner", ScytheSpinner).display is False
            assert "refused to draw" in str(altar.query_one("#status").render())

    asyncio.run(scenario())


def test_the_fleet_is_released_even_when_a_grave_fails(tmp_path, monkeypatch):
    manifest = tmp_path / "necropolis.toml"
    manifest.write_text("[[grave]]\nsource = '/no/such/crypt'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(tmp_path))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            board = await _enter(app, pilot, "necropolis")
            board.action_reap_fleet()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert board._reaping is False
            assert board.query_one("#spinner", ScytheSpinner).display is False
            assert "1 failed" in str(board.query_one("#status").render())

    asyncio.run(scenario())


# -- the console's own furniture ----------------------------------------------


def test_console_menu_drives_with_arrows_and_completes_with_tab(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            console.query_one("#incant", Input).value = "/s"
            await pilot.pause()
            menu = console.query_one("#suggestions", OptionList)
            first = menu.get_option_at_index(0).id
            await pilot.press("down")
            await pilot.pause()
            assert menu.highlighted == 1
            await pilot.press("up")
            await pilot.pause()
            assert menu.highlighted == 0
            await pilot.press("tab")
            await pilot.pause()
            assert console.query_one("#incant", Input).value == f"{first} "
            assert menu.display is False

    asyncio.run(scenario())


def test_console_escape_closes_the_menu_before_leaving(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            console.query_one("#incant", Input).value = "/cen"
            await pilot.pause()
            assert console.query_one("#suggestions", OptionList).display is True
            console.action_dismiss_or_crypt()  # first escape: the menu
            await pilot.pause()
            assert console.query_one("#suggestions", OptionList).display is False
            assert app.screen is console
            console.action_dismiss_or_crypt()  # second: the door
            await pilot.pause()
            assert isinstance(app.screen, CryptMapScreen)

    asyncio.run(scenario())


def test_console_lists_recipes_and_switches_theme(tmp_path, monkeypatch):
    rc = tmp_path / ".reaperrc"
    rc.write_text(
        "[recipes.nightly]\ncommand = 'census'\nargs = ['.']\ndescription = 'the nightly count'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(tmp_path))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            log = console.query_one("#console-log", TextArea)
            box = console.query_one("#incant", Input)

            box.value = "/recipes"
            await pilot.press("enter")
            await pilot.pause()
            assert "nightly" in log.text and "the nightly count" in log.text

            box.value = "/theme"
            await pilot.press("enter")
            await pilot.pause()
            assert "reaper-dracula" in log.text  # no name: it lists them

            box.value = "/theme textual-light"
            await pilot.press("enter")
            await pilot.pause()
            assert app.theme == "textual-light"

            box.value = "/theme nosferatu"
            await pilot.press("enter")
            await pilot.pause()
            assert "no theme 'nosferatu'" in log.text

    asyncio.run(scenario())


def test_console_saves_the_last_artifact(necropolis, tmp_path):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            box = console.query_one("#incant", Input)

            console.action_save_artifact()  # nothing cast yet
            await pilot.pause()
            assert app.screen is console

            box.value = f"census {necropolis}"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            target = tmp_path / "out" / "artifact.md"
            box.value = f"/save {target}"
            await pilot.press("enter")
            await pilot.pause()
            assert "total_files" in target.read_text() or target.read_text().strip()

    asyncio.run(scenario())


def test_console_reports_a_ritual_that_fails(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            console.query_one("#incant", Input).value = "census /no/such/crypt"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log = console.query_one("#console-log", TextArea).text
            assert "the ritual failed" in log
            assert console.query_one("#spinner", ScytheSpinner).display is False

    asyncio.run(scenario())


def test_console_help_modal_opens(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            console = await _enter(app, pilot, "console")
            console.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


# -- the coven's step editor ---------------------------------------------------


def test_coven_adds_removes_and_reorders_steps(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            assert len(coven._steps) == 1

            await pilot.click("#step-add")
            await pilot.pause()
            assert len(coven._steps) == 2
            coven.query_one("#step-command", Select).value = "census"
            await pilot.pause()
            assert coven._steps[1].command == "census"

            await pilot.click("#step-up")  # census moves above limbs
            await pilot.pause()
            assert [s.command for s in coven._steps] == ["census", "limbs"]
            await pilot.click("#step-down")
            await pilot.pause()
            assert [s.command for s in coven._steps] == ["limbs", "census"]

            await pilot.click("#step-remove")
            await pilot.pause()
            assert len(coven._steps) == 1
            await pilot.click("#step-remove")  # the last step: the form empties
            await pilot.pause()
            assert coven._steps == []
            assert "(no steps yet)" in str(coven.query_one("#rite-incantation").render())

    asyncio.run(scenario())


def test_coven_refuses_to_run_a_rite_with_no_steps(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            coven._steps = []
            coven._step_index = None
            coven.action_run()
            await pilot.pause()
            assert coven._rite_running is False
            assert coven.query_one("#results", DataTable).row_count == 0

    asyncio.run(scenario())


def test_coven_records_a_step_that_fails_and_keeps_going(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            coven.query_one("#rite-sources", Input).value = "/no/such/crypt"
            await pilot.pause()
            coven.action_run()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "1 failed" in str(coven.query_one("#status").render())
            assert coven._rite_running is False

    asyncio.run(scenario())


def test_coven_row_shows_its_artifact_and_help_opens(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            coven = await _enter(app, pilot, "coven")
            coven.query_one("#rite-sources", Input).value = str(necropolis)
            await pilot.pause()
            coven.action_run()
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = coven.query_one("#results", DataTable)
            table.action_select_cursor()
            await pilot.pause()
            assert coven.query_one("#results-preview", TextArea).text.strip()
            coven.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


# -- the sanctum's own doors ---------------------------------------------------


def test_the_palette_knows_every_chamber(necropolis):
    from git_reaper.tui.app import ChamberCommands

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            provider = ChamberCommands(app.screen)
            discovered = [hit.display async for hit in provider.discover()]
            assert len(discovered) == len(CHAMBERS)

            await provider.startup()
            hits = [hit async for hit in provider.search("altar")]
            assert hits, "the palette cannot find the altar"
            hits[0].command()  # walking through the door is what a hit does
            await pilot.pause()
            assert isinstance(app.screen, AltarScreen)

    asyncio.run(scenario())


def test_the_crypt_map_opens_a_door_and_explains_itself(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            crypt = app.screen
            assert isinstance(crypt, CryptMapScreen)
            crypt.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()

            doors = crypt.query_one("#doors", OptionList)
            doors.action_select()  # enter on the highlighted door
            await pilot.pause()
            assert isinstance(app.screen, AltarScreen)

    asyncio.run(scenario())


# -- the boards' edges ---------------------------------------------------------


def test_necropolis_board_reports_a_missing_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(tmp_path))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            board = await _enter(app, pilot, "necropolis")
            assert "no manifest" in str(board.query_one("#status").render())
            board.action_reap_fleet()  # nothing loaded: refuses, does not run
            await pilot.pause()
            assert board._reaping is False
            board._row_selected_by_name("nobody")
            await pilot.pause()
            assert "no artifact yet" in str(board.query_one("#status").render())
            board.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


def test_reliquary_exports_the_slab_and_survives_a_bad_source(make_repo, tmp_path):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(root))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            reliquary = await _enter(app, pilot, "reliquary")
            reliquary.action_export()  # nothing triaged yet
            await pilot.pause()
            assert app.screen is reliquary

            reliquary.action_triage()
            await app.workers.wait_for_complete()
            await pilot.pause()
            target = tmp_path / "slab.md"
            reliquary._write_export(str(target))
            assert "the reliquary" in target.read_text()
            assert AWS_KEY not in target.read_text()  # masked on the way out

            reliquary.query_one("#source", Input).value = "/no/such/crypt"
            reliquary.action_triage()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "the triage failed" in str(reliquary.query_one("#status").render())
            assert reliquary.query_one("#spinner", ScytheSpinner).display is False

    asyncio.run(scenario())


def test_seance_reads_one_commit_and_survives_a_bad_ref(necropolis):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            seance = await _enter(app, pilot, "seance")
            await app.workers.wait_for_complete()
            await pilot.pause()

            commits = seance.query_one("#hour-commits", DataTable)
            commits.action_select_cursor()
            await pilot.pause()
            detail = seance.query_one("#board-preview", TextArea).text
            assert "commit " in detail and "author:" in detail

            seance.action_scry()  # no ref A: it asks instead of running
            await pilot.pause()
            seance.query_one("#ref-a", Input).value = "no-such-tag"
            seance.action_scry()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "the seance failed" in str(seance.query_one("#status").render())
            assert seance.query_one("#spinner", ScytheSpinner).display is False

    asyncio.run(scenario())


# -- the altar's remaining furniture -------------------------------------------


def test_altar_copies_saves_and_toggles_the_rendered_view(necropolis, tmp_path):
    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")

            altar.action_copy()  # nothing reaped yet: it says so, it does not crash
            altar.action_save()
            await pilot.pause()
            assert app.screen is altar

            altar.action_reap()
            await app.workers.wait_for_complete()
            await pilot.pause()

            altar.action_copy()
            await pilot.pause()
            altar.action_toggle_rendered()  # limbs is markdown: the rendered view opens
            await pilot.pause()
            assert altar.query_one("#rendered").display is True
            assert altar.query_one("#preview").display is False
            altar.action_toggle_rendered()
            await pilot.pause()
            assert altar.query_one("#preview").display is True

            altar._last_format = "json"  # a raw artifact has no rendered view
            altar.action_toggle_rendered()
            await pilot.pause()
            assert altar.query_one("#preview").display is True

            target = tmp_path / "deep" / "artifact.md"
            altar._write_artifact(str(target))
            assert target.read_text().startswith("```")
            altar._write_artifact(None)  # a cancelled save writes nothing

    asyncio.run(scenario())


def test_altar_reports_a_source_that_is_not_there(make_dir):
    folder = make_dir({"a.txt": "hi\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(folder))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            await app.workers.wait_for_complete()
            await pilot.pause()

            altar._inspect_source("/no/such/crypt")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "no such path" in str(altar.query_one("#source-hint").render())

            altar._inspect_source("https://example.com/repo.git")
            await pilot.pause()
            assert "remote source" in str(altar.query_one("#source-hint").render())

    asyncio.run(scenario())


def test_a_stale_inspection_never_overwrites_a_newer_one(make_dir, necropolis):
    # an exclusive worker cancels its predecessor, but the thread runs on and
    # still calls back -- the slow answer about the old source must not land.
    folder = make_dir({"a.txt": "hi\n"})

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            await app.workers.wait_for_complete()
            await pilot.pause()

            altar._inspect_source(str(necropolis))  # the source we are on now
            await app.workers.wait_for_complete()
            await pilot.pause()
            altar._show_source_state(str(folder), "plain folder (history rituals will fail)", False)
            await pilot.pause()
            assert "git repo" in str(altar.query_one("#source-hint").render())

    asyncio.run(scenario())


def test_altar_recipe_lands_the_new_flags_on_the_widgets(tmp_path, monkeypatch):
    rc = tmp_path / ".reaperrc"
    rc.write_text(
        "[recipes.deep]\ncommand = 'limbs'\n"
        "args = ['.', '--depth', '2', '--sizes', '--exclude', '*.lock', '--format', 'json']\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(tmp_path))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            recipes = altar.query_one("#recipes", OptionList)
            recipes.highlighted = 0
            recipes.action_select()
            await pilot.pause()

            assert altar.current_op.key == "limbs"
            assert altar.query_one("#opt-depth", Input).value == "2"
            assert altar.query_one("#opt-sizes", Switch).value is True
            assert altar.query_one("#opt-exclude", Input).value == "*.lock"
            assert altar.query_one("#opt-format", Select).value == "json"
            assert "loaded deep" in str(altar.query_one("#status").render())

    asyncio.run(scenario())


def test_altar_says_so_when_a_recipe_is_not_a_chamber_ritual(tmp_path, monkeypatch):
    rc = tmp_path / ".reaperrc"
    rc.write_text("[recipes.odd]\ncommand = 'pulse'\nargs = []\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(tmp_path))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            altar = await _enter(app, pilot, "altar")
            recipes = altar.query_one("#recipes", OptionList)
            recipes.highlighted = 0
            recipes.action_select()
            await pilot.pause()
            assert "not a chamber ritual" in str(altar.query_one("#status").render())

    asyncio.run(scenario())


# -- the grimoire --------------------------------------------------------------


def test_grimoire_reports_a_miswritten_book(tmp_path, monkeypatch):
    (tmp_path / ".reaperrc").write_text("[recipes.broken]\nargs = ['.']\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(tmp_path))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            grimoire = await _enter(app, pilot, "grimoire")
            assert "miswritten" in str(grimoire.query_one("#status").render())

    asyncio.run(scenario())


def test_grimoire_refuses_a_nameless_recipe_and_opens_its_help(necropolis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            grimoire = await _enter(app, pilot, "grimoire")

            grimoire.action_delete_recipe()  # nothing named
            await pilot.pause()
            assert "pick or name" in str(grimoire.query_one("#status").render())

            grimoire.action_save_recipe()  # a recipe with no name cannot be cast
            await pilot.pause()
            assert "name" in str(grimoire.query_one("#status").render()).lower()

            grimoire.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


def test_grimoire_starts_a_new_recipe_from_the_list(necropolis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = ReaperApp(source=str(necropolis))
        async with app.run_test(size=(120, 45)) as pilot:
            await pilot.pause()
            grimoire = await _enter(app, pilot, "grimoire")
            recipes = grimoire.query_one("#recipes", OptionList)
            recipes.highlighted = 0  # "(new recipe)"
            recipes.action_select()
            await pilot.pause()
            assert grimoire.query_one("#recipe-name", Input).value == ""
            assert "reaper limbs" in str(grimoire.query_one("#incantation").render())

    asyncio.run(scenario())
