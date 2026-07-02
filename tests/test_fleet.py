"""The necropolis: manifests, fan-out, and the combined index."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_reaper.core import fleet


def _manifest(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "necropolis.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_manifest_parses_graves(tmp_path):
    path = _manifest(
        tmp_path,
        """
        [[grave]]
        source = "https://github.com/x/alpha.git"
        tags = ["docs"]

        [[grave]]
        source = "/local/beta"
        name = "beta-prime"
        """,
    )
    graves = fleet.load_manifest(path)
    assert graves[0] == fleet.Grave(
        name="alpha", source="https://github.com/x/alpha.git", tags=("docs",)
    )
    assert graves[1].name == "beta-prime"


@pytest.mark.parametrize(
    "text",
    [
        "",  # no graves at all
        "[[grave]]\nname = 'x'\n",  # no source
        "[[grave]]\nsource = '/a/same'\n[[grave]]\nsource = '/b/same'\n",  # name clash
        "[[grave]]\nsource = '/a'\ntags = 'docs'\n",  # tags not a list
    ],
)
def test_miswritten_manifests_are_refused(tmp_path, text):
    with pytest.raises(fleet.FleetError):
        fleet.load_manifest(_manifest(tmp_path, text))


def test_missing_manifest_names_the_file(tmp_path):
    with pytest.raises(fleet.FleetError, match=r"necropolis\.toml"):
        fleet.load_manifest(tmp_path / "necropolis.toml")


def test_derive_name_strips_the_shroud():
    assert fleet.derive_name("https://github.com/x/repo.git") == "repo"
    assert fleet.derive_name("/home/john/graves/dig/") == "dig"


def test_artifact_extension_follows_format():
    assert fleet.artifact_extension([]) == ".md"
    assert fleet.artifact_extension(["--format", "json"]) == ".json"
    assert fleet.artifact_extension(["--format=csv"]) == ".csv"
    assert fleet.artifact_extension(["-f", "html"]) == ".html"


def _fake_runner(outcomes: dict[str, int]):
    """A runner that writes a fake artifact and returns a scripted exit code."""
    calls: list[list[str]] = []

    def run(argv: list[str]) -> int:
        calls.append(argv)
        source = argv[1]
        out = Path(argv[argv.index("--out") + 1])
        code = outcomes.get(source, 0)
        if code != 1:  # failed rituals leave no artifact
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(f"reaped {source}\n")
        return code

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_fanout_runs_every_grave_and_writes_the_index(tmp_path):
    graves = [
        fleet.Grave(name="alpha", source="/graves/alpha"),
        fleet.Grave(name="beta", source="/graves/beta"),
    ]
    runner = _fake_runner({})
    result = fleet.necropolis("census", ["--format", "json"], graves, tmp_path / "out", runner)
    assert [c[0] for c in runner.calls] == ["census", "census"]
    assert all(o.ok for o in result.graves)
    assert (tmp_path / "out" / "alpha.json").is_file()
    index = Path(result.index).read_text()
    assert "| alpha |" in index and "2 of 2 graves reaped" in index
    assert fleet.fleet_exit_code(result) == 0


def test_one_failed_grave_does_not_stop_the_fleet(tmp_path):
    graves = [
        fleet.Grave(name="good", source="/g/good"),
        fleet.Grave(name="bad", source="/g/bad"),
        fleet.Grave(name="cursed", source="/g/cursed"),
    ]
    result = fleet.necropolis(
        "exhume", [], graves, tmp_path / "out", _fake_runner({"/g/bad": 1, "/g/cursed": 3})
    )
    fates = {o.name: o for o in result.graves}
    assert fates["good"].ok
    assert not fates["bad"].ok and fates["bad"].artifact == ""
    assert fates["cursed"].exit_code == 3
    index = Path(result.index).read_text()
    assert "cursed" in index and "failed" in index
    assert fleet.fleet_exit_code(result) == 1  # a failure outranks a curse


def test_curse_without_failure_exits_3(tmp_path):
    graves = [fleet.Grave(name="cursed", source="/g/cursed")]
    runner = _fake_runner({"/g/cursed": 3})
    result = fleet.necropolis("exhume", [], graves, tmp_path / "out", runner)
    assert fleet.fleet_exit_code(result) == 3


def test_tag_filters_the_graves(tmp_path):
    graves = [
        fleet.Grave(name="doc", source="/g/doc", tags=("docs",)),
        fleet.Grave(name="code", source="/g/code"),
    ]
    runner = _fake_runner({})
    result = fleet.necropolis("harvest", [], graves, tmp_path / "out", runner, tag="docs")
    assert [o.name for o in result.graves] == ["doc"]


def test_a_runner_exception_is_contained(tmp_path):
    def explode(argv: list[str]) -> int:
        raise RuntimeError("the ground opened")

    result = fleet.necropolis(
        "census", [], [fleet.Grave(name="a", source="/g/a")], tmp_path / "out", explode
    )
    (outcome,) = result.graves
    assert not outcome.ok and "the ground opened" in outcome.error
    assert fleet.fleet_exit_code(result) == 1
