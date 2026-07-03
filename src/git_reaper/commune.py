"""The communion: git-reaper as an MCP server.

A fourth face on the same engine (library, CLI, TUI, and now agents). The
tool layer is one more thin adapter over the typed core: every read-only
ritual in the TUI's operation catalog becomes an agent-callable tool whose
input schema is derived from the ritual's option specs and whose output is
the same provenance-stamped JSON the CLI prints. `commune` only adapts; the
core does the work.

Guardrails, all opt-in to loosen:

- Read-only by default; `resurrect`, `reanimate`, and `banish` appear only
  with allow_write. `veil` is always available: it scrubs text in flight and
  touches no disk.
- Offline by default; `plague` is forced to manifest parsing unless
  allow_network.
- Rooted: an agent may only reap local paths under the allowed roots and
  remote URLs on the allowed hosts. Defaults to the launch source only.
- Secrets stay masked: exhume over MCP returns the same masked previews it
  prints anywhere else.

This module is importable without the [mcp] extra; only `serve` needs it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from git_reaper import cache, config, tui_ops
from git_reaper.core import graveyard as graveyard_core
from git_reaper.core import history as history_core
from git_reaper.core import rules as rules_core
from git_reaper.core import scry as scry_core
from git_reaper.core import unpack as unpack_core
from git_reaper.core.source import looks_remote, resolve_source
from git_reaper.formatters import jsonfmt
from git_reaper.models import RepoRef

SERVER_NAME = "git-reaper"


class CommuneError(ValueError):
    """A request the guardrails refuse."""


@dataclass(frozen=True)
class Guard:
    """What the server may touch: local roots, remote hosts, and the toggles."""

    roots: tuple[Path, ...]
    hosts: tuple[str, ...] = ()
    allow_write: bool = False
    allow_network: bool = False

    def check(self, source: str) -> None:
        """Refuse sources outside the allowlist. Raises CommuneError."""
        if looks_remote(source):
            host = urlparse(source if "://" in source else f"ssh://{source}").hostname or ""
            if host not in self.hosts:
                raise CommuneError(
                    f"host {host!r} is outside the circle (allowed: {list(self.hosts) or 'none'})"
                )
            return
        path = Path(source).expanduser().resolve()
        if not any(path == root or path.is_relative_to(root) for root in self.roots):
            raise CommuneError(
                f"path {str(path)!r} is outside the circle "
                f"(allowed roots: {[str(r) for r in self.roots]})"
            )


@dataclass(frozen=True)
class ToolSpec:
    """One agent-callable ritual: name, contract, and the handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]


def _opt_schema(opt: tui_ops.OptSpec) -> dict[str, Any]:
    """One option spec as a JSON-schema property."""
    if isinstance(opt, tui_ops.ChoiceOpt):
        return {"type": "string", "enum": list(opt.choices), "description": opt.label}
    if isinstance(opt, tui_ops.ToggleOpt):
        return {"type": "boolean", "description": opt.label}
    if isinstance(opt, tui_ops.NumberOpt):
        return {"type": "integer", "description": opt.label}
    return {"type": "string", "description": opt.label}


def _source_property(default_source: str) -> dict[str, Any]:
    return {
        "type": "string",
        "description": f"Path or repo URL to reap (default: {default_source!r}). "
        "Must be inside the server's allowed roots or hosts.",
    }


@dataclass
class Communion:
    """The assembled server state: guardrails, default source, and the tools."""

    default_source: str
    guard: Guard
    tools: dict[str, ToolSpec] = field(default_factory=dict)

    # -- resolution ---------------------------------------------------------

    def _resolve(self, args: dict[str, Any], needs_git: bool) -> RepoRef:
        source = str(args.get("source") or self.default_source)
        self.guard.check(source)
        # History rituals need real history; remote clones go full-depth.
        depth = None if needs_git else 1
        return resolve_source(source, depth=depth).repo

    # -- handlers -----------------------------------------------------------

    def _op_handler(self, op: tui_ops.Operation) -> Callable[[dict[str, Any]], str]:
        def run(args: dict[str, Any]) -> str:
            repo = self._resolve(args, op.needs_git)
            opts = op.defaults()
            for key in opts:
                if key in args:
                    opts[key] = args[key]
            if "format" in opts:
                opts["format"] = "json"
            if op.key == "plague" and not self.guard.allow_network:
                opts["offline"] = True  # the crypt stays sealed
            with tui_ops.invoker("reaper commune"):
                return op.run(repo, opts).text

        return run

    def _autopsy(self, args: dict[str, Any]) -> str:
        repo = self._resolve(args, needs_git=True)
        result = history_core.autopsy(
            repo,
            str(args["path"]),
            follow=bool(args.get("follow", True)),
            invoked="reaper commune (autopsy)",
        )
        return jsonfmt.render(result)

    def _scry(self, args: dict[str, Any]) -> str:
        repo = self._resolve(args, needs_git=True)
        limit = args.get("limit")
        result = scry_core.scry(
            repo,
            str(args["ref_a"]),
            str(args["ref_b"]),
            limit=int(limit) if limit is not None else None,
            invoked="reaper commune (scry)",
        )
        return jsonfmt.render(result)

    def _grimoire(self, args: dict[str, Any]) -> str:
        return jsonfmt.render(config.load_grimoire())

    def _resurrect(self, args: dict[str, Any]) -> str:
        repo = self._resolve(args, needs_git=True)
        result = graveyard_core.resurrect(
            repo,
            str(args["path"]),
            out=Path(repo.path),
            force=bool(args.get("force", False)),
        )
        return jsonfmt.render(result)

    def _veil(self, args: dict[str, Any]) -> str:
        text = str(args["text"])
        rules = rules_core.load_rules(config.custom_rules())
        repo = RepoRef(source="mcp", kind="local", path=".")
        result, veiled = rules_core.veil(
            text,
            "mcp",
            repo,
            rules=rules,
            with_entropy=not bool(args.get("no_entropy", False)),
            invoked="reaper commune (veil)",
        )
        return json.dumps(
            {"report": jsonfmt.to_jsonable(result), "veiled": veiled}, ensure_ascii=False
        )

    def _reanimate(self, args: dict[str, Any]) -> str:
        out = Path(str(args["out"])).expanduser().resolve()
        self.guard.check(str(out))  # the risen tree must land inside the circle
        result = unpack_core.reanimate(
            str(args["text"]),
            out,
            force=bool(args.get("force", False)),
            verify=bool(args.get("verify", False)),
        )
        return jsonfmt.render(result)

    def _banish(self, args: dict[str, Any]) -> str:
        older = args.get("older_than")
        seconds = cache.parse_age(str(older)) if older else None
        return jsonfmt.render(cache.banish(older_than_seconds=seconds))

    # -- catalog ------------------------------------------------------------

    def build(self, only: tuple[str, ...] | None = None) -> None:
        """Assemble the tool catalog, optionally restricted to `only` names."""
        specs: list[ToolSpec] = []
        for op in tui_ops.OPERATIONS:
            props: dict[str, Any] = {"source": _source_property(self.default_source)}
            for opt in op.options:
                if opt.name == "format":
                    continue  # tools always return JSON; formats are a human thing
                props[opt.name] = _opt_schema(opt)
            note = " Needs git history." if op.needs_git else ""
            specs.append(
                ToolSpec(
                    name=op.key,
                    description=f"{op.description} ({op.group}).{note}",
                    input_schema={"type": "object", "properties": props},
                    handler=self._op_handler(op),
                )
            )
        source_prop = _source_property(self.default_source)
        specs.append(
            ToolSpec(
                "autopsy",
                "Deep single-file exam: birth, renames, authors, churn, line age."
                " Needs git history.",
                {
                    "type": "object",
                    "properties": {
                        "source": source_prop,
                        "path": {"type": "string", "description": "File path inside the repo."},
                        "follow": {"type": "boolean", "description": "Follow renames."},
                    },
                    "required": ["path"],
                },
                self._autopsy,
            )
        )
        specs.append(
            ToolSpec(
                "scry",
                "Compare two refs: churn, most-changed files, and new souls in A..B."
                " Needs git history.",
                {
                    "type": "object",
                    "properties": {
                        "source": source_prop,
                        "ref_a": {"type": "string", "description": "The older ref."},
                        "ref_b": {"type": "string", "description": "The newer ref."},
                        "limit": {"type": "integer", "description": "Top N files."},
                    },
                    "required": ["ref_a", "ref_b"],
                },
                self._scry,
            )
        )
        specs.append(
            ToolSpec(
                "grimoire",
                "Effective git-reaper configuration and stored recipes.",
                {"type": "object", "properties": {}},
                self._grimoire,
            )
        )
        specs.append(
            ToolSpec(
                "veil",
                "Scrub secrets and configured patterns from artifact text before it"
                " leaves the crypt. Returns the veiled text and the receipt; touches"
                " no disk.",
                {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The artifact text to veil."},
                        "no_entropy": {
                            "type": "boolean",
                            "description": "Signatures only; skip the entropy sweep.",
                        },
                    },
                    "required": ["text"],
                },
                self._veil,
            )
        )
        if self.guard.allow_write:
            specs.append(
                ToolSpec(
                    "reanimate",
                    "Reconstruct a directory tree from a packed (conjure) artifact."
                    " The target must sit inside the allowed roots. (write)",
                    {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "The packed artifact."},
                            "out": {"type": "string", "description": "Target directory."},
                            "force": {
                                "type": "boolean",
                                "description": "Write into a non-empty directory.",
                            },
                            "verify": {
                                "type": "boolean",
                                "description": "Check per-file sha256 meta.",
                            },
                        },
                        "required": ["text", "out"],
                    },
                    self._reanimate,
                )
            )
            specs.append(
                ToolSpec(
                    "resurrect",
                    "Restore a dead file's last living bytes into the working tree."
                    " Needs git history. (write)",
                    {
                        "type": "object",
                        "properties": {
                            "source": source_prop,
                            "path": {"type": "string", "description": "The dead file's path."},
                            "force": {"type": "boolean", "description": "Overwrite if present."},
                        },
                        "required": ["path"],
                    },
                    self._resurrect,
                )
            )
            specs.append(
                ToolSpec(
                    "banish",
                    "Clear the clone cache (the catacombs). (write)",
                    {
                        "type": "object",
                        "properties": {
                            "older_than": {
                                "type": "string",
                                "description": "Only graves older than this, e.g. '7d'.",
                            }
                        },
                    },
                    self._banish,
                )
            )
        if only is not None:
            unknown = set(only) - {spec.name for spec in specs}
            if unknown:
                raise CommuneError(f"unknown tools in the commune allowlist: {sorted(unknown)}")
            specs = [spec for spec in specs if spec.name in only]
        self.tools = {spec.name: spec for spec in specs}

    def call(self, name: str, args: dict[str, Any]) -> str:
        spec = self.tools.get(name)
        if spec is None:
            raise CommuneError(f"no such ritual: {name!r}")
        return spec.handler(args)

    # -- resources ----------------------------------------------------------

    RESOURCES: tuple[tuple[str, str, str], ...] = (
        ("reaper://grimoire", "grimoire", "Effective configuration and recipes (JSON)."),
        ("reaper://tombstone", "tombstone", "Stats card for the default source (JSON)."),
        ("reaper://census", "census", "File-type census for the default source (JSON)."),
    )

    def read_resource(self, uri: str) -> str:
        if uri == "reaper://grimoire":
            return jsonfmt.render(config.load_grimoire())
        if uri == "reaper://tombstone":
            repo = self._resolve({}, needs_git=True)
            return jsonfmt.render(
                history_core.tombstone(repo, invoked="reaper commune (tombstone)")
            )
        if uri == "reaper://census":
            return self.call("census", {})
        raise CommuneError(f"no such resource: {uri!r}")


# --------------------------------------------------------------------------
# prompts -- sane default workflows, no prompt archaeology required
# --------------------------------------------------------------------------

PROMPTS: dict[str, tuple[str, str]] = {
    "pack-this-repo": (
        "Pack a repo for review: structure, contents, and size.",
        "Use the git-reaper tools to prepare {source} for review: run `census` to "
        "size it, `bones` for the structural map, and `conjure` to pack the full "
        "contents. Summarize what the repo is and how it is laid out.",
    ),
    "audit-this-repo": (
        "Audit a repo: secrets, risk hotspots, and dependency advisories.",
        "Audit {source} with the git-reaper tools: run `exhume` for committed "
        "secrets, `omens` for the riskiest files, and `plague` for dependency "
        "advisories. Report findings ranked by severity, citing the provenance "
        "block of each artifact.",
    ),
    "explain-this-repo": (
        "Explain a repo: what it is, who built it, and how it moves.",
        "Explain {source} using the git-reaper tools: `tombstone` for the vital "
        "stats, `bones` for the structure, and `souls` for who built it. Write a "
        "short orientation for a new contributor.",
    ),
}


def render_prompt(name: str, source: str) -> str:
    if name not in PROMPTS:
        raise CommuneError(f"no such prompt: {name!r}")
    return PROMPTS[name][1].format(source=source)


# --------------------------------------------------------------------------
# assembly and serving (everything below needs the [mcp] extra)
# --------------------------------------------------------------------------


def assemble(
    source: str = ".",
    roots: tuple[str, ...] = (),
    hosts: tuple[str, ...] = (),
    allow_write: bool = False,
    allow_network: bool = False,
    only: tuple[str, ...] | None = None,
) -> Communion:
    """Build the communion from flags layered over the grimoire's [commune]."""
    settings = config.commune_settings()
    root_strs = list(roots) or list(settings.get("roots", []))
    host_list = list(hosts) or list(settings.get("hosts", []))
    tool_list = only if only is not None else settings.get("tools")
    root_paths = [Path(r).expanduser().resolve() for r in root_strs]
    # The launch source is always inside the circle.
    if looks_remote(source):
        launch_host = urlparse(source if "://" in source else f"ssh://{source}").hostname
        if launch_host and launch_host not in host_list:
            host_list.append(launch_host)
    elif not root_paths:
        root_paths = [Path(source).expanduser().resolve()]
    guard = Guard(
        roots=tuple(root_paths),
        hosts=tuple(host_list),
        allow_write=allow_write or bool(settings.get("allow_write", False)),
        allow_network=allow_network or bool(settings.get("allow_network", False)),
    )
    communion = Communion(default_source=source, guard=guard)
    communion.build(only=tuple(tool_list) if tool_list is not None else None)
    return communion


def build_server(communion: Communion) -> Any:
    """Wire the communion into an MCP low-level Server (needs the extra)."""
    import anyio
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from pydantic import AnyUrl

    from git_reaper import __version__

    server: Server[Any, Any] = Server(SERVER_NAME, version=__version__)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(name=s.name, description=s.description, inputSchema=s.input_schema)
            for s in communion.tools.values()
        ]

    @server.call_tool()
    async def call_tool(name: str, args: dict[str, Any]) -> list[types.TextContent]:
        text = await anyio.to_thread.run_sync(communion.call, name, args)
        return [types.TextContent(type="text", text=text)]

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(uri=AnyUrl(uri), name=name, description=desc)
            for uri, name, desc in communion.RESOURCES
        ]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        return await anyio.to_thread.run_sync(communion.read_resource, str(uri))

    @server.list_prompts()
    async def list_prompts() -> list[types.Prompt]:
        return [
            types.Prompt(
                name=name,
                description=desc,
                arguments=[
                    types.PromptArgument(
                        name="source", description="Path or repo URL.", required=False
                    )
                ],
            )
            for name, (desc, _template) in PROMPTS.items()
        ]

    @server.get_prompt()
    async def get_prompt(name: str, args: dict[str, str] | None) -> types.GetPromptResult:
        source = (args or {}).get("source") or communion.default_source
        text = render_prompt(name, source)
        return types.GetPromptResult(
            description=PROMPTS[name][0],
            messages=[
                types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))
            ],
        )

    return server


def serve(communion: Communion, http: str | None = None) -> None:
    """Run the MCP server: stdio by default, HTTP when asked."""
    import anyio

    server = build_server(communion)
    if http:
        _serve_http(server, http)
        return

    from mcp.server.stdio import stdio_server

    async def _run_stdio() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_run_stdio)


def _serve_http(server: Any, address: str) -> None:
    """The shared-reaper transport: streamable HTTP on host:port."""
    import contextlib
    from collections.abc import AsyncIterator

    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.types import Receive, Scope, Send

    host, _, port_str = address.rpartition(":")
    if not host or not port_str.isdigit():
        raise CommuneError(f"--http wants HOST:PORT, got {address!r}")

    manager = StreamableHTTPSessionManager(app=server, stateless=True)

    async def handle(scope: Scope, receive: Receive, send: Send) -> None:
        await manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    app = Starlette(routes=[Mount("/mcp", app=handle)], lifespan=lifespan)
    uvicorn.run(app, host=host, port=int(port_str), log_level="warning")
