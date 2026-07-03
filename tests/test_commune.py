"""The communion: the MCP adapter's catalog, guardrails, and wire contract.

The adapter (assemble/build/call) is importable without the [mcp] extra;
only the wire tests at the bottom need it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from git_reaper import commune, config, tui_ops

HISTORY = [
    {"message": "birth", "write": {"README.md": "# corpse\n", "src/app.py": "x = 1\n"}},
    {"message": "fix: rot", "when": "2020-02-01T00:00:00", "write": {"src/app.py": "x = 2\n"}},
    {"message": "burial", "when": "2020-03-01T00:00:00", "delete": ["README.md"]},
]


@pytest.fixture
def communion(make_history) -> commune.Communion:
    root = make_history(HISTORY)
    return commune.assemble(str(root))


# -- catalog -----------------------------------------------------------------


def test_catalog_covers_every_source_ritual(communion: commune.Communion):
    expected = {op.key for op in tui_ops.OPERATIONS} | {"autopsy", "scry", "grimoire", "veil"}
    assert set(communion.tools) == expected


def test_write_rituals_are_hidden_until_allowed(make_history):
    root = make_history(HISTORY)
    writers = {"resurrect", "reanimate", "banish"}
    sealed = commune.assemble(str(root))
    assert not writers & set(sealed.tools)
    open_crypt = commune.assemble(str(root), allow_write=True)
    assert writers <= set(open_crypt.tools)


def test_tools_speak_json_not_formats(communion: commune.Communion):
    # formats are a human thing; every tool schema takes a source, never a format
    for spec in communion.tools.values():
        props = spec.input_schema["properties"]
        assert "format" not in props, spec.name
        if spec.name not in ("grimoire", "veil"):  # these take no source at all
            assert "source" in props, spec.name


def test_option_specs_become_schema_properties(communion: commune.Communion):
    omens = communion.tools["omens"].input_schema["properties"]
    assert omens["lens"]["enum"] == ["all", "churn", "bugs", "age", "size"]
    assert omens["limit"]["type"] == "integer"
    assert communion.tools["unfinished"].input_schema["properties"]["age"]["type"] == "boolean"


def test_tool_allowlist_restricts_and_validates(make_history):
    root = make_history(HISTORY)
    narrow = commune.assemble(str(root), only=("census", "limbs"))
    assert set(narrow.tools) == {"census", "limbs"}
    with pytest.raises(commune.CommuneError, match="banshee"):
        commune.assemble(str(root), only=("banshee",))


# -- guardrails ---------------------------------------------------------------


def test_guard_refuses_paths_outside_the_circle(communion: commune.Communion, tmp_path: Path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(commune.CommuneError, match="outside the circle"):
        communion.call("census", {"source": str(outside)})


def test_guard_hosts():
    guard = commune.Guard(roots=(), hosts=("github.com",))

    # URL-style remotes
    guard.check("https://github.com/o/r")  # allowed
    with pytest.raises(commune.CommuneError, match=r"gitlab\.com"):
        guard.check("https://gitlab.com/o/r")

    # scp-style remotes are normalized to ssh:// and respect the same allowlist
    guard.check("git@github.com:o/r")  # allowed
    with pytest.raises(commune.CommuneError, match=r"gitlab\.com"):
        guard.check("git@gitlab.com:o/r")


def test_launch_source_host_is_always_allowed():
    remote = commune.assemble("https://github.com/o/r")
    assert "github.com" in remote.guard.hosts


def test_plague_never_leaves_the_crypt_uninvited(communion: commune.Communion):
    result = json.loads(communion.call("plague", {"offline": False}))
    assert result["checked"] is False  # forced offline without allow_network


# -- calls --------------------------------------------------------------------


def test_census_returns_provenance_stamped_json(communion: commune.Communion):
    result = json.loads(communion.call("census", {}))
    assert result["provenance"]["invoked"] == "reaper commune (census)"
    assert result["provenance"]["schema"] == "census/v1"


def test_autopsy_and_scry_take_their_extra_arguments(communion: commune.Communion):
    autopsy = json.loads(communion.call("autopsy", {"path": "src/app.py"}))
    assert autopsy["path"] == "src/app.py"
    scry = json.loads(communion.call("scry", {"ref_a": "HEAD~2", "ref_b": "HEAD"}))
    assert scry["commits"] == 2


def test_resurrect_writes_only_when_allowed(make_history):
    root = make_history(HISTORY)
    risen = commune.assemble(str(root), allow_write=True)
    result = json.loads(risen.call("resurrect", {"path": "README.md"}))
    assert (root / "README.md").read_text() == "# corpse\n"
    assert result["path"] == "README.md"


def test_veil_scrubs_in_flight(communion: commune.Communion):
    leaky = "token = 'AKIAIOSFODNN7EXAMPLE'\n"
    result = json.loads(communion.call("veil", {"text": leaky}))
    assert "AKIAIOSFODNN7EXAMPLE" not in result["veiled"]
    assert "[VEILED:" in result["veiled"]
    assert result["report"]["total"] >= 1
    assert result["report"]["provenance"]["invoked"] == "reaper commune (veil)"


def test_reanimate_round_trip_stays_inside_the_circle(make_history, tmp_path: Path):
    root = make_history(HISTORY)
    risen = commune.assemble(str(root), allow_write=True)
    packed = risen.call("conjure", {})
    grave = root / "risen"
    result = json.loads(risen.call("reanimate", {"text": packed, "out": str(grave)}))
    assert (grave / "src/app.py").read_text() == "x = 2\n"
    assert result["out"] == str(grave)
    outside = tmp_path / "elsewhere-risen"
    with pytest.raises(commune.CommuneError, match="outside the circle"):
        risen.call("reanimate", {"text": packed, "out": str(outside)})


def test_unknown_ritual_raises(communion: commune.Communion):
    with pytest.raises(commune.CommuneError, match="wraith"):
        communion.call("wraith", {})


# -- resources and prompts ------------------------------------------------------


def test_resources_read(communion: commune.Communion):
    tomb = json.loads(communion.read_resource("reaper://tombstone"))
    assert tomb["commits"] == 3
    with pytest.raises(commune.CommuneError):
        communion.read_resource("reaper://banshee")


def test_prompts_render_with_the_source():
    text = commune.render_prompt("audit-this-repo", "/tmp/crypt")
    assert "/tmp/crypt" in text and "exhume" in text
    with pytest.raises(commune.CommuneError):
        commune.render_prompt("banshee", ".")


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("127.0.0.1:6666", ("127.0.0.1", 6666)),
        ("crypt.local:80", ("crypt.local", 80)),
        ("[::1]:6666", ("::1", 6666)),  # IPv6 wants brackets
    ],
)
def test_http_address_parses(address: str, expected: tuple[str, int]):
    assert commune.parse_http_address(address) == expected


@pytest.mark.parametrize("address", ["6666", "host:", ":6666", "host:zed", "[::1]", "a:99999"])
def test_http_address_rejects_malformed(address: str):
    with pytest.raises(commune.CommuneError, match="HOST:PORT"):
        commune.parse_http_address(address)


# -- grimoire [commune] table ---------------------------------------------------


def test_commune_settings_read_and_validate(tmp_path: Path):
    (tmp_path / ".reaperrc").write_text('[commune]\nroots = ["/a", "/b"]\nallow_write = true\n')
    settings = config.commune_settings(tmp_path)
    assert settings == {"roots": ["/a", "/b"], "allow_write": True}


def test_assemble_honors_the_commune_table(tmp_path: Path, monkeypatch):
    # the CLI + config layering end-to-end: flags absent, the grimoire rules
    (tmp_path / ".reaperrc").write_text(
        "[commune]\n"
        'roots = ["/circle"]\n'
        'hosts = ["github.com"]\n'
        "allow_write = true\n"
        "allow_network = true\n"
        'tools = ["census", "exhume", "banish"]\n'
    )
    monkeypatch.chdir(tmp_path)
    communion = commune.assemble(str(tmp_path))
    # roots are resolved on assembly; on Windows that also gains the drive
    assert communion.guard.roots == (Path("/circle").resolve(),)
    assert communion.guard.hosts == ("github.com",)
    assert communion.guard.allow_write is True
    assert communion.guard.allow_network is True
    assert set(communion.tools) == {"census", "exhume", "banish"}


@pytest.mark.parametrize(
    "body",
    [
        "[commune]\nbanshee = true\n",  # unknown key
        "[commune]\nallow_write = 'yes'\n",  # wrong type
        "[commune]\nroots = [1, 2]\n",  # not strings
    ],
)
def test_commune_settings_reject_bad_tables(tmp_path: Path, body: str):
    (tmp_path / ".reaperrc").write_text(body)
    with pytest.raises(config.GrimoireError):
        config.commune_settings(tmp_path)


# -- the wire (needs the [mcp] extra) --------------------------------------------


def test_over_the_wire(make_history):
    mcp = pytest.importorskip("mcp")
    del mcp
    import anyio
    from mcp.shared.memory import create_connected_server_and_client_session

    root = make_history(HISTORY)
    server = commune.build_server(commune.assemble(str(root)))

    async def scenario() -> None:
        async with create_connected_server_and_client_session(server) as session:
            tools = await session.list_tools()
            assert {"census", "exhume", "grimoire"} <= {t.name for t in tools.tools}

            called = await session.call_tool("census", {})
            payload = json.loads(called.content[0].text)
            assert payload["provenance"]["invoked"] == "reaper commune (census)"

            refused = await session.call_tool("census", {"source": "/etc"})
            assert refused.isError and "outside the circle" in refused.content[0].text

            prompts = await session.list_prompts()
            assert {p.name for p in prompts.prompts} == set(commune.PROMPTS)

    anyio.run(scenario)


def test_positional_rituals_keep_their_dedicated_mcp_tools(communion: commune.Communion):
    # autopsy and veil joined the TUI catalog, but the communion keeps the
    # richer bespoke tools: `follow` (not `no_follow`) for autopsy, raw
    # `text` (never a disk path) for veil -- one tool per name, no shadowing.
    autopsy = communion.tools["autopsy"].input_schema
    assert autopsy["required"] == ["path"]
    assert "follow" in autopsy["properties"] and "no_follow" not in autopsy["properties"]
    veil = communion.tools["veil"].input_schema
    assert "text" in veil["properties"] and "file" not in veil["properties"]
    # lineage flows through the generic catalog handler; its needle is required
    lineage = communion.tools["lineage"].input_schema
    assert lineage["required"] == ["needle"]
