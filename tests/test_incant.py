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
    assert "one source only" in incant.parse("census a b").error
    assert incant.parse("").kind == "empty"
    assert "unreadable" in incant.parse('census "unclosed').error


def test_flag_help_and_render_help_cover_every_ritual():
    text = incant.render_help()
    for op in OPERATIONS:
        assert f"- `{op.key} [SOURCE]" in text
    for meta in incant.META_COMMANDS:
        assert meta in text
