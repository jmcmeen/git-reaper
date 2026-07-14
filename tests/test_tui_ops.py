"""The TUI operation registry: the thin adapter's correctness, no Textual.

Runs in the base suite. These lock that each ritual is wired to its own core
function and formatter (the copy-paste risk across a dozen near-identical
entries), that options actually reach the core, and that history rituals are
flagged as needing a repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from git_reaper import tui_ops
from git_reaper.gitio import GitError
from git_reaper.models import RepoRef

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"


def ref(root: Path) -> RepoRef:
    return RepoRef(source=str(root), kind="local", path=str(root))


#: The positional rituals need their argument; sweeps supply canonical ones
#: that exist in both the necropolis fixture and the plain-folder tests.
POSITIONALS: dict[str, dict[str, str]] = {
    "autopsy": {"path": "README.md"},
    "lineage": {"needle": "x = 1"},
    "veil": {"file": "README.md"},
}


def _run(op: tui_ops.Operation, root: Path, **overrides: object) -> tui_ops.ReapResult:
    opts = op.defaults()
    opts.update(POSITIONALS.get(op.key, {}))
    if "out" in opts:  # writing rituals land in the throwaway tree, never the cwd
        opts["out"] = str(root.parent / f"{op.key}-out")
    opts.update(overrides)
    return op.run(ref(root), opts)


def test_registry_keys_are_unique_and_indexed():
    keys = [op.key for op in tui_ops.OPERATIONS]
    assert len(keys) == len(set(keys))
    assert set(tui_ops.OPERATIONS_BY_KEY) == set(keys)


# -- parity with the CLI -------------------------------------------------------
#
# The chambers must offer what `reaper <key> --help` offers, or the TUI quietly
# becomes a lesser tool. These read the real Typer app, so a flag added to the
# CLI and forgotten in the registry fails here rather than in a user's hands.

#: Flags no chamber offers, and why. `--out`/`--schema` are CLI plumbing (a
#: chamber saves with `s` and never prints a schema); the CI gates exit 3
#: instead of drawing, and a chamber badges what it found instead.
_CLI_ONLY = {"--out", "--schema", "--help", "--fail-on", "--fail-over"}

#: Per-ritual omissions, each deliberate.
_CLI_ONLY_PER_OP = {
    # the *clone* depth. One Sanctum source is reaped by ritual after ritual,
    # so the crypt is always dug whole; a shallow one would blind whichever
    # history ritual came next. (limbs' --depth is a tree depth, and is offered.)
    "harvest": {"--depth"},
    "conjure": {"--depth"},
    "scavenge": {"--depth"},
    # veil --report writes a second file; a chamber shows one artifact.
    "veil": {"--report"},
}


def _cli_params(key: str) -> list[set[str]]:
    """One set of long names per CLI parameter -- aliases ride together, so
    `--pattern/--glob` counts as one thing a chamber must offer, not two."""
    import typer

    from git_reaper.cli import app as cli_app

    command = typer.main.get_command(cli_app).commands[key]  # type: ignore[attr-defined]
    groups = [{opt for opt in param.opts if opt.startswith("--")} for param in command.params]
    return [group for group in groups if group]


def _tui_flags(op: tui_ops.Operation) -> set[str]:
    """Every flag the chamber's option panel renders (the positional is not one)."""
    return {"--" + spec.name.replace("_", "-") for spec in op.options if spec.name != op.positional}


@pytest.mark.parametrize("op", tui_ops.OPERATIONS, ids=lambda op: op.key)
def test_every_chamber_option_is_a_real_cli_flag(op):
    known = {opt for group in _cli_params(op.key) for opt in group}
    unknown = _tui_flags(op) - known
    assert not unknown, f"{op.key} offers {unknown}, which `reaper {op.key}` does not take"


@pytest.mark.parametrize("op", tui_ops.OPERATIONS, ids=lambda op: op.key)
def test_every_cli_flag_is_offered_by_its_chamber(op):
    omitted = _CLI_ONLY | _CLI_ONLY_PER_OP.get(op.key, set())
    if op.positional:  # rides as the CLI's positional argument, not as a flag
        omitted.add("--" + op.positional)
    if op.source_arg == "flag":  # `autopsy PATH -s SOURCE`: the chamber's source box
        omitted.add("--source")
    offered = _tui_flags(op)
    missing = [
        group for group in _cli_params(op.key) if not (group & offered) and not (group & omitted)
    ]
    assert not missing, f"{op.key} does not offer {missing}, which `reaper {op.key}` takes"


def test_every_operation_belongs_to_a_known_group():
    for op in tui_ops.OPERATIONS:
        assert op.group in tui_ops.GROUPS, op.key


def test_each_operation_renders_its_own_artifact(necropolis):
    # A repo satisfies both git and non-git operations. Every ritual must
    # produce an artifact that names its own schema (the anti-copy-paste lock).
    for op in tui_ops.OPERATIONS:
        result = _run(op, necropolis)
        assert result.text.strip(), op.key
        if op.key == "tombstone":
            assert "R I P" in result.text  # art card, not a schema table
        elif op.key == "limbs":
            assert result.text.startswith("```") and "directories," in result.text
        elif op.key == "harvest":
            assert "git-reaper harvest" in result.text  # harvest has no schema line
        elif op.key == "veil":
            assert "# hi" in result.text  # the scrubbed artifact itself, no banner
        elif op.key == "scavenge":
            assert "nothing was written" in result.text  # the fixture holds no skills
        else:
            assert f"schema:    {op.key}/v1" in result.text, op.key


def test_reap_result_carries_a_summary(necropolis):
    for op in tui_ops.OPERATIONS:
        assert _run(op, necropolis).summary, op.key


def test_history_operations_are_flagged():
    needs = {op.key for op in tui_ops.OPERATIONS if op.needs_git}
    assert needs == {
        "chronicle",
        "souls",
        "haunt",
        "autopsy",
        "lineage",
        "graveyard",
        "rot",
        "ghosts",
        "tombstone",
        "exhume",
        "omens",
        "wake",
        "possession",
        "revenant",
        "prophecy",
        "exorcise",
        "ward",
    }


def test_non_git_operations_work_on_a_plain_folder(make_dir):
    folder = make_dir({"README.md": "# hi\n", "a.py": "x = 1\n"})
    for op in tui_ops.OPERATIONS:
        if op.needs_git:
            continue
        assert _run(op, folder).text.strip(), op.key


def test_history_operation_on_a_plain_folder_errors(make_dir):
    folder = make_dir({"a.txt": "hi\n"})
    chronicle = tui_ops.OPERATIONS_BY_KEY["chronicle"]
    with pytest.raises(GitError):
        _run(chronicle, folder)


# -- options actually reach the core -----------------------------------------


def test_format_option_dispatches_to_each_formatter(necropolis):
    census = tui_ops.OPERATIONS_BY_KEY["census"]
    assert _run(census, necropolis, format="md").text.startswith("<!--")
    assert _run(census, necropolis, format="json").text.lstrip().startswith("{")
    assert "extension,language" in _run(census, necropolis, format="csv").text
    assert _run(census, necropolis, format="html").text.startswith("<!DOCTYPE html>")


def test_lens_option_changes_omens(necropolis):
    omens = tui_ops.OPERATIONS_BY_KEY["omens"]
    all_lens = _run(omens, necropolis, lens="all", format="json").text
    size_lens = _run(omens, necropolis, lens="size", format="json").text
    assert '"lens": "all"' in all_lens
    assert '"lens": "size"' in size_lens


def test_heatmap_toggle_changes_souls(necropolis):
    souls = tui_ops.OPERATIONS_BY_KEY["souls"]
    with_heatmap = _run(souls, necropolis, heatmap=True).text
    without = _run(souls, necropolis, heatmap=False).text
    assert "activity" in with_heatmap and "activity" not in without


def test_cursed_flag_on_a_leaky_repo(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})
    result = _run(tui_ops.OPERATIONS_BY_KEY["exhume"], root)
    assert result.cursed
    assert AWS_KEY not in result.text  # masked, always
    clean = make_repo({"ok.md": "nothing\n"}, name="clean")
    assert not _run(tui_ops.OPERATIONS_BY_KEY["exhume"], clean).cursed


def test_exhume_since_option_narrows_the_scan(make_history):
    root = make_history(
        [
            {"message": "old secret", "write": {"a.txt": f"{AWS_KEY}\n"}, "tag": "v1"},
            {"message": "new secret", "write": {"b.txt": "ghp_" + "a1B2" * 9 + "\n"}},
        ]
    )
    exhume = tui_ops.OPERATIONS_BY_KEY["exhume"]
    full = _run(exhume, root, format="json")
    since = _run(exhume, root, since="v1", format="json")
    assert "aws-access-key" in full.text and "github-token" in full.text
    assert "aws-access-key" not in since.text and "github-token" in since.text


def test_defaults_cover_every_option():
    for op in tui_ops.OPERATIONS:
        defaults = op.defaults()
        assert set(defaults) == {opt.name for opt in op.options}, op.key


# -- the options the CLI has always had, now that the chambers have them too --


def test_ref_option_reaches_the_crypt(necropolis):
    # the ref rides on the *resolution*, not the ritual: the crypt is opened at
    # that ref, and every history core reads through it (git log <ref>).
    on_main = tui_ops.resolve(str(necropolis), {})
    on_feature = tui_ops.resolve(str(necropolis), {"ref": "feature"})
    assert on_feature.repo.ref == "feature"

    chronicle = tui_ops.OPERATIONS_BY_KEY["chronicle"]
    opts = chronicle.defaults()
    main_text = chronicle.run(on_main.repo, opts).summary
    feature_text = chronicle.run(on_feature.repo, opts).summary
    # the feature branch carries one commit main never saw
    assert main_text == "5 commits"
    assert feature_text == "6 commits"


def test_exclude_option_skips_globs(necropolis):
    census = tui_ops.OPERATIONS_BY_KEY["census"]
    everything = _run(census, necropolis)
    without_md = _run(census, necropolis, exclude="*.md, *.py")
    assert ".md" in everything.text
    assert ".md" not in without_md.text and ".py" not in without_md.text


def test_limbs_offers_the_trees_own_shape(necropolis):
    limbs = tui_ops.OPERATIONS_BY_KEY["limbs"]
    assert "README.md" in _run(limbs, necropolis).text
    assert "README.md" not in _run(limbs, necropolis, dirs_only=True).text
    assert "src" in _run(limbs, necropolis, dirs_only=True).text
    # depth 1 keeps the top level's crypts but never descends into them
    shallow = _run(limbs, necropolis, depth=1).text
    assert "src" in shallow and "main.py" not in shallow
    assert "lines" in _run(limbs, necropolis, lines=True, sizes=True).text


def test_harvest_takes_a_pattern_and_a_cap(necropolis):
    harvest = tui_ops.OPERATIONS_BY_KEY["harvest"]
    assert "README.md" in _run(harvest, necropolis).text  # the default *.md
    only_py = _run(harvest, necropolis, pattern="*.py")
    assert "main.py" in only_py.text and "README.md" not in only_py.text


def test_conjure_can_veil_and_hash_while_it_packs(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})
    conjure = tui_ops.OPERATIONS_BY_KEY["conjure"]
    assert AWS_KEY in _run(conjure, root).text
    veiled = _run(conjure, root, veil=True).text
    assert AWS_KEY not in veiled  # the secret never leaves in the bundle
    assert "sha256" in _run(conjure, root, sha256=True).text


def test_chronicle_max_count_takes_only_the_newest(necropolis):
    chronicle = tui_ops.OPERATIONS_BY_KEY["chronicle"]
    assert _run(chronicle, necropolis).summary == "5 commits"
    assert _run(chronicle, necropolis, max_count=2).summary == "2 commits"


def test_possession_threshold_and_its_bounds(necropolis):
    possession = tui_ops.OPERATIONS_BY_KEY["possession"]
    assert ">= 100%" in _run(possession, necropolis, threshold=1.0).text
    assert ">= 10%" in _run(possession, necropolis, threshold=0.1).text
    with pytest.raises(ValueError, match="between 0 and 1"):
        _run(possession, necropolis, threshold=1.5)
    with pytest.raises(ValueError, match="must be a number"):
        _run(possession, necropolis, threshold="most of it")


def test_wake_since_and_revenant_fixes_reach_their_cores(necropolis):
    wake = tui_ops.OPERATIONS_BY_KEY["wake"]
    assert "since v1.0.0" in _run(wake, necropolis, since="v1.0.0").summary
    revenant = tui_ops.OPERATIONS_BY_KEY["revenant"]
    assert _run(revenant, necropolis, fixes=1).text.strip()


def test_exorcise_can_skip_the_secret_pass(make_repo):
    root = make_repo({"leak.env": f"KEY={AWS_KEY}\n"})
    exorcise = tui_ops.OPERATIONS_BY_KEY["exorcise"]
    assert _run(exorcise, root).cursed  # the secret is a body to expel
    assert not _run(exorcise, root, no_secrets=True).cursed  # bloat only, and it is small


def test_a_size_option_speaks_the_cli_s_size_grammar(necropolis):
    doppelgangers = tui_ops.OPERATIONS_BY_KEY["doppelgangers"]
    assert _run(doppelgangers, necropolis, min_size="4KB").text.strip()
    with pytest.raises(ValueError):
        _run(doppelgangers, necropolis, min_size="a handful")


# -- incantation args (the headless twin) ------------------------------------


def test_incantation_args_default_opts_are_silent():
    for op in tui_ops.OPERATIONS:
        opts = op.defaults()
        # souls' heatmap and plague's offline default True in the TUI; those
        # flags still appear so the CLI run matches what the chamber showed.
        args = tui_ops.incantation_args(op, opts)
        for arg in args:
            assert arg.startswith("--"), (op.key, args)


def test_incantation_args_render_each_spec_kind():
    omens = tui_ops.OPERATIONS_BY_KEY["omens"]
    args = tui_ops.incantation_args(omens, {"lens": "churn", "limit": 20, "format": "json"})
    assert args == ["--lens", "churn", "--limit", "20", "--format", "json"]
    souls = tui_ops.OPERATIONS_BY_KEY["souls"]
    assert tui_ops.incantation_args(souls, {"heatmap": True, "format": "md"}) == ["--heatmap"]
    assert tui_ops.incantation_args(souls, {"heatmap": False, "format": "md"}) == []
    ghosts = tui_ops.OPERATIONS_BY_KEY["ghosts"]
    assert tui_ops.incantation_args(ghosts, {"than": "90d", "format": "md"}) == ["--than", "90d"]


def test_incantation_args_underscores_become_dashes():
    exhume = tui_ops.OPERATIONS_BY_KEY["exhume"]
    args = tui_ops.incantation_args(exhume, {"no_entropy": True, "format": "md"})
    assert args == ["--no-entropy"]


# -- triage (the Reliquary) ---------------------------------------------------


def test_triage_merges_rituals_and_sorts_by_severity(make_repo):
    root = make_repo({"config.py": 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n', "notes.md": "fine\n"})
    report = tui_ops.triage(ref(root))
    assert report.rows, "the planted secret must reach the slab"
    assert report.cursed  # exhume found something
    assert report.rows == sorted(report.rows, key=lambda r: (-r.severity, r.ritual, r.subject))
    top = report.rows[0]
    assert top.ritual == "exhume" and top.subject == "config.py"
    assert "AKIAABCDEFGHIJKLMNOP" not in top.detail  # masked, never the raw secret
    assert "exhume 1" in report.summary


def test_triage_on_a_plain_folder_reports_errors_not_a_crash(make_dir):
    folder = make_dir({"a.md": "hi\n"})
    report = tui_ops.triage(ref(folder))
    assert not report.cursed
    assert report.errors  # exhume/omens/rot need history and say so
    assert any("exhume" in e for e in report.errors)


def test_render_triage_is_a_markdown_slab(make_repo):
    root = make_repo({"config.py": 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n'})
    text = tui_ops.render_triage(tui_ops.triage(ref(root)))
    assert text.startswith("# the reliquary")
    assert "| ---: | --- | --- | --- |" in text
    assert "exhume" in text


# -- the positional rituals: autopsy, lineage, veil ---------------------------


def test_autopsy_examines_one_file(necropolis):
    result = _run(tui_ops.OPERATIONS_BY_KEY["autopsy"], necropolis)
    assert "README.md" in result.text
    assert "commits" in result.summary


def test_lineage_finds_the_origin(necropolis):
    result = _run(tui_ops.OPERATIONS_BY_KEY["lineage"], necropolis)
    assert "first summoned" in result.summary


def test_veil_masks_a_planted_secret(make_dir):
    folder = make_dir({"leak.md": f"key = {AWS_KEY}\n"})
    result = _run(tui_ops.OPERATIONS_BY_KEY["veil"], folder, file="leak.md")
    assert AWS_KEY not in result.text
    assert "[VEILED:" in result.text
    assert "replacements" in result.summary


def test_veil_anchors_relative_files_to_the_source(make_dir, tmp_path):
    folder = make_dir({"inner.md": "clean\n"})
    result = _run(tui_ops.OPERATIONS_BY_KEY["veil"], folder, file="inner.md")
    assert result.text == "clean\n"
    with pytest.raises(ValueError, match="no such artifact"):
        _run(tui_ops.OPERATIONS_BY_KEY["veil"], folder, file="elsewhere.md")


def test_positional_rituals_refuse_an_empty_argument(necropolis):
    for key, positional in (("autopsy", "path"), ("lineage", "needle"), ("veil", "file")):
        with pytest.raises(ValueError, match=positional):
            _run(tui_ops.OPERATIONS_BY_KEY[key], necropolis, **{positional: " "})


def test_incantation_argv_speaks_the_true_cli_grammar():
    autopsy = tui_ops.OPERATIONS_BY_KEY["autopsy"]
    opts = autopsy.defaults() | {"path": "src/app.py", "no_follow": True}
    assert tui_ops.incantation_argv(autopsy, ".", opts) == ["src/app.py", "--no-follow"]
    assert tui_ops.incantation_argv(autopsy, "/crypt", opts) == [
        "src/app.py",
        "-s",
        "/crypt",
        "--no-follow",
    ]
    veil = tui_ops.OPERATIONS_BY_KEY["veil"]
    v_opts = veil.defaults() | {"file": "PACKED.md"}
    assert tui_ops.incantation_argv(veil, "/anywhere", v_opts) == ["PACKED.md"]
    limbs = tui_ops.OPERATIONS_BY_KEY["limbs"]
    assert tui_ops.incantation_argv(limbs, ".", limbs.defaults()) == ["."]
