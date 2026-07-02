"""The shared rules engine: detection, masking, veiling, and exhumation."""

from __future__ import annotations

import json

import pytest

from git_reaper.core import rules
from git_reaper.core.source import resolve_source
from git_reaper.formatters.markdown import render_exhume, render_veil
from git_reaper.gitio import GitError

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"
GITHUB_TOKEN = "ghp_" + "a1B2" * 9  # 36 chars after the prefix
HIGH_ENTROPY = "kJ8/xQ2mN9+pL4vR7sT1uW3yZ5bC6dE8fG0hAiqo"


def _repo(make_repo, files):
    return resolve_source(str(make_repo(files))).repo


# -- scanning ----------------------------------------------------------------


def test_signatures_find_the_usual_suspects():
    text = f"a = '{AWS_KEY}'\ntoken = '{GITHUB_TOKEN}'\n-----BEGIN RSA PRIVATE KEY-----\n"
    found = {m.rule.name for m in rules.scan_text(text)}
    assert {"aws-access-key", "github-token", "private-key"} <= found


def test_match_carries_the_line_number():
    text = f"line one\nline two\nkey = '{AWS_KEY}'\n"
    (match,) = [m for m in rules.scan_text(text) if m.rule.name == "aws-access-key"]
    assert match.line == 3


def test_entropy_sweep_catches_formatless_secrets():
    matches = rules.scan_text(f"blob = '{HIGH_ENTROPY}'\n")
    assert any(m.rule.name == rules.ENTROPY_RULE for m in matches)


def test_hex_shas_do_not_trip_the_entropy_wire():
    sha = "3f9a1c2e8b7d6a5f4e3d2c1b0a9f8e7d6c5b4a39"
    assert rules.scan_text(f"commit = '{sha}'\n") == []


def test_entropy_sweep_can_be_disabled():
    assert rules.scan_text(f"blob = '{HIGH_ENTROPY}'\n", with_entropy=False) == []


def test_overlapping_rules_first_wins():
    # sk-ant- keys also look like openai keys; the specific rule claims first.
    text = "key = 'sk-ant-" + "a1b2c3d4" * 6 + "'"
    names = [m.rule.name for m in rules.scan_text(text)]
    assert names.count("anthropic-key") == 1
    assert "openai-key" not in names


def test_mask_never_shows_the_middle():
    masked = rules.mask(AWS_KEY)
    assert masked == "AKIA...MNOP"
    assert AWS_KEY[4:-4] not in masked
    assert rules.mask("tiny") == "ti..."


def test_custom_rules_extend_the_builtins():
    loaded = rules.load_rules({"corp-host": {"pattern": r"\w+\.corp\.example\.com"}})
    matches = rules.scan_text("db01.corp.example.com", rules=loaded)
    assert [m.rule.name for m in matches] == ["corp-host"]


@pytest.mark.parametrize(
    "spec",
    [
        {"severity": "high"},  # no pattern
        {"pattern": "x", "severity": "apocalyptic"},
        {"pattern": "(unclosed"},
    ],
)
def test_miswritten_custom_rules_are_refused(spec):
    with pytest.raises(rules.RuleError):
        rules.load_rules({"bad": spec})


# -- veiling -----------------------------------------------------------------


def test_veil_text_replaces_and_tallies():
    veiled = rules.veil_text(f"key={AWS_KEY} mail bob@example.com bis bob@example.com\n")
    assert "[VEILED:aws-access-key]" in veiled.text
    assert veiled.text.count("[VEILED:email]") == 2
    assert AWS_KEY not in veiled.text
    assert veiled.counts["email"] == 2
    assert veiled.total == 3


def test_veil_result_renders_without_the_secret(make_dir):
    root = make_dir({"a.md": "x\n"})
    repo = resolve_source(str(root)).repo
    result, text = rules.veil(f"key={AWS_KEY}\n", "a.md", repo, generated="2026-07-01T00:00:00Z")
    assert AWS_KEY not in text and AWS_KEY not in render_veil(result)
    assert result.total == 1


def test_scrub_veils_log_lines():
    assert AWS_KEY not in rules.scrub(f"debug: token {AWS_KEY} rejected")


# -- exhume ------------------------------------------------------------------


def test_exhume_digs_deleted_secrets_out_of_history(make_history):
    root = make_history(
        [
            {"message": "oops", "write": {"config/old.env": f"AWS_KEY={AWS_KEY}\n"}},
            {"message": "remove it", "delete": ["config/old.env"]},
        ]
    )
    result = rules.exhume(resolve_source(str(root)).repo)
    (finding,) = [f for f in result.findings if f.rule == "aws-access-key"]
    assert finding.path == "config/old.env"
    assert finding.preview == "AKIA...MNOP"
    assert AWS_KEY not in json.dumps(finding.__dict__)  # the contract
    assert finding.sha  # attributed to the commit that buried it
    assert result.blobs_scanned > 0


def test_lockfiles_skip_the_entropy_sweep_but_not_signatures(make_repo):
    # a lock file is full of legitimate high-entropy hashes; the entropy sweep
    # must not cry wolf over it, but a real signature match still fires.
    repo = _repo(
        make_repo,
        {"uv.lock": f"hash = '{HIGH_ENTROPY}'\nkey = '{AWS_KEY}'\n"},
    )
    rules_hit = {f.rule for f in rules.exhume(repo).findings}
    assert "aws-access-key" in rules_hit
    assert rules.ENTROPY_RULE not in rules_hit


def test_exhume_refuses_plain_folders(make_dir):
    with pytest.raises(GitError):
        rules.exhume(resolve_source(str(make_dir({"a.md": "x\n"}))).repo)


def test_baseline_suppresses_known_findings(make_repo, tmp_path):
    repo = _repo(make_repo, {"leak.txt": f"{AWS_KEY}\n"})
    first = rules.exhume(repo)
    assert first.findings
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps([f.fingerprint for f in first.findings]))
    second = rules.exhume(repo, baseline=rules.load_baseline(baseline))
    assert second.findings == []
    assert second.suppressed == len(first.findings)


def test_baseline_accepts_a_previous_json_report(tmp_path):
    report = {"findings": [{"fingerprint": "abc123"}]}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    assert rules.load_baseline(path) == {"abc123"}


def test_unreadable_baseline_is_an_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json")
    with pytest.raises(rules.RuleError):
        rules.load_baseline(path)


def test_cursed_gates(make_repo):
    repo = _repo(make_repo, {"leak.txt": f"{AWS_KEY}\n", "hunch.txt": f"{HIGH_ENTROPY}\n"})
    result = rules.exhume(repo)
    assert rules.cursed(result, "any")
    assert rules.cursed(result, "high")
    clean_root = make_repo({"ok.md": "nothing here\n"}, name="clean")
    clean = rules.exhume(resolve_source(str(clean_root)).repo)
    assert not rules.cursed(clean, "any")
    with pytest.raises(rules.RuleError):
        rules.cursed(result, "sometimes")


def test_exhume_report_renders_masked(make_repo):
    result = rules.exhume(_repo(make_repo, {"leak.txt": f"{AWS_KEY}\n"}))
    text = render_exhume(result)
    assert "AKIA...MNOP" in text and AWS_KEY not in text
