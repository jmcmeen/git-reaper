"""The incantation console's brain: suggest, parse, validate."""

from __future__ import annotations

from git_reaper import incant
from git_reaper.tui_ops import OPERATIONS


def test_suggest_empty_lists_every_ritual_and_meta():
    texts = {s.text for s in incant.suggest("")}
    assert {f"/{op.key}" for op in OPERATIONS} <= texts
    assert set(incant.META_COMMANDS) <= texts


def test_suggest_ranks_prefix_over_substring_over_subsequence():
    ranked = [s.text for s in incant.suggest("/om")]
    assert ranked[0] == "/omens"
    assert "/hnt" not in ranked
    assert "/haunt" in [s.text for s in incant.suggest("hnt")]  # subsequence


def test_parse_ritual_with_flags_builds_opts_and_argv():
    spell = incant.parse("/omens . --lens churn --limit 5 --format json")
    assert spell.kind == "ritual" and spell.op is not None
    assert spell.op.key == "omens"
    assert spell.source == "."
    assert spell.opts["lens"] == "churn" and spell.opts["limit"] == 5
    expected = ("reaper", "omens", ".", "--lens", "churn", "--limit", "5", "--format", "json")
    assert spell.argv == expected


def test_parse_uses_cli_toggle_semantics():
    bare = incant.parse("souls")
    assert bare.kind == "ritual"
    assert bare.opts["heatmap"] is False  # absent flag means off, as in the CLI
    flagged = incant.parse("souls --heatmap")
    assert flagged.opts["heatmap"] is True
    assert flagged.argv == ("reaper", "souls", ".", "--heatmap")


def test_parse_accepts_a_pasted_cli_line():
    spell = incant.parse("reaper census /tmp/crypt --format csv")
    assert spell.kind == "ritual" and spell.op is not None and spell.op.key == "census"
    assert spell.source == "/tmp/crypt"


def test_parse_meta_commands_carry_their_argument():
    save = incant.parse("/save out/spooky.md")
    assert save.kind == "meta" and save.meta == "/save" and save.meta_arg == "out/spooky.md"
    assert incant.parse("/clear").kind == "meta"


def test_parse_errors_are_specific():
    assert "did you mean /omens" in incant.parse("/omen").error
    assert "takes no --nope" in incant.parse("census --nope").error
    assert "needs a value" in incant.parse("omens --lens").error
    assert "must be one of" in incant.parse("omens --lens spooky").error
    assert "whole number" in incant.parse("haunt --limit soon").error
    assert "one too many" in incant.parse("census a b").error
    assert incant.parse("").kind == "empty"
    assert "unreadable" in incant.parse('census "unclosed').error


def test_flag_help_and_render_help_cover_every_ritual():
    text = incant.render_help()
    for op in OPERATIONS:
        assert f"- `{incant.usage(op)}" in text
    for meta in incant.META_COMMANDS:
        assert meta in text


# -- the positional rituals: bare tokens fill the CLI grammar in order --------


def test_parse_positional_then_source():
    spell = incant.parse("/autopsy src/app.py /crypt --no-follow")
    assert spell.kind == "ritual" and spell.op is not None and spell.op.key == "autopsy"
    assert spell.opts["path"] == "src/app.py"
    assert spell.source == "/crypt"
    assert spell.argv == ("reaper", "autopsy", "src/app.py", "-s", "/crypt", "--no-follow")


def test_parse_positional_default_source_stays_silent():
    spell = incant.parse('/lineage "def main" --regex')
    assert spell.kind == "ritual"
    assert spell.opts["needle"] == "def main"
    assert spell.source == "."
    assert spell.argv == ("reaper", "lineage", "def main", "--regex")


def test_parse_missing_positional_is_a_clear_error():
    assert "needs a path" in incant.parse("/autopsy").error
    assert "needs a needle" in incant.parse("/lineage --regex").error
    assert "needs a file" in incant.parse("/veil").error


def test_parse_veil_takes_a_file_and_no_source():
    spell = incant.parse("/veil PACKED.md")
    assert spell.kind == "ritual"
    assert spell.opts["file"] == "PACKED.md"
    assert spell.argv == ("reaper", "veil", "PACKED.md")
    assert "one too many" in incant.parse("/veil PACKED.md extra").error


def test_usage_shapes_follow_the_cli_grammar():
    by_key = {op.key: op for op in OPERATIONS}
    assert incant.usage(by_key["autopsy"]) == "autopsy PATH [SOURCE]"
    assert incant.usage(by_key["veil"]) == "veil FILE"
    assert incant.usage(by_key["census"]) == "census [SOURCE]"


# -- the option kinds the CLI's flags need ------------------------------------


def test_parse_repeats_a_list_flag_the_way_the_cli_does():
    spell = incant.parse("/census . --exclude '*.lock' --exclude dist")
    assert spell.kind == "ritual"
    assert spell.opts["exclude"] == "*.lock dist"
    # and it round-trips back out as two flags, not one joined string
    assert spell.argv == ("reaper", "census", ".", "--exclude", "*.lock", "--exclude", "dist")


def test_parse_takes_a_fractional_threshold():
    spell = incant.parse("/possession . --threshold 0.9")
    assert spell.kind == "ritual"
    assert spell.opts["threshold"] == 0.9
    assert spell.argv == ("reaper", "possession", ".", "--threshold", "0.9")
    assert "needs a number" in incant.parse("/possession . --threshold most").error


def test_a_default_valued_flag_stays_out_of_the_incantation():
    # the twin should be as short as what a human would type
    spell = incant.parse("/possession . --threshold 0.75")  # the CLI's own default
    assert spell.argv == ("reaper", "possession", ".")


def test_flag_help_names_every_option_shape():
    by_key = {op.key: op for op in OPERATIONS}
    assert "--threshold X.Y" in incant.flag_help(by_key["possession"])
    assert "--exclude TEXT (repeatable)" in incant.flag_help(by_key["census"])
    assert "--limit N" in incant.flag_help(by_key["haunt"])
    assert "--format {md|json}" in incant.flag_help(by_key["bones"])
