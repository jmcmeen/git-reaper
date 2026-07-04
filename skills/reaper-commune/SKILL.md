---
name: reaper-commune
description: Give an agent (or a fleet of agents) controlled, read-only-by-default access to a codebase via git-reaper's MCP server (`reaper commune`) — root/host restrictions, write and network gates, shared resources and prompts. Use when asked to expose a repo to an agent over MCP, set up or connect to a reaper MCP server, share one codebase across several agents safely, or restrict what an agent can read, write, or reach over the network.
---

`reaper commune` (needs `pip install "git-reaper[mcp]"`) serves every git-reaper
ritual as an MCP tool: same provenance-stamped JSON the CLI prints, no shell
required on the agent's side. It runs over stdio (one process per session,
what most MCP clients spawn themselves) or HTTP (one shared server, several
clients). Everything is locked down until you widen it explicitly — that
narrow-by-default posture is the point when the caller on the other end is an
agent, not you.

## Stand it up

```sh
reaper commune .                                  # stdio, rooted to .
reaper commune . --http 127.0.0.1:6666             # HTTP at /mcp instead
```

Connect a client:

```sh
# stdio: the client spawns the process itself
claude mcp add reaper -- reaper commune /path/to/repo --root /path/to/repo

# HTTP: the client just needs the URL
claude mcp add --transport http reaper http://127.0.0.1:6666/mcp
```

## The guardrails (each one widens the circle explicitly)

| Flag | Default | What it allows |
| --- | --- | --- |
| `--root PATH` (repeatable) | only the launch source | Reap local paths under `PATH`. |
| `--host HOST` (repeatable) | none | Clone and reap repos from a remote host (e.g. `github.com`). |
| `--allow-write` | off | Expose the writing tools: `reanimate`, `resurrect`, `banish`, `scavenge`. |
| `--allow-network` | off | Let `plague` consult the OSV database instead of parsing manifests offline. |

Everything else — `limbs`, `census`, `bones`, `chronicle`, `souls`, `haunt`,
`exhume`, `omens`, `plague` (offline), `veil`, and the rest of the read-only
rituals — is on by default and never touches disk outside the allowed roots.
`veil` in particular takes raw text and returns it scrubbed, no file
involved, so it's safe to expose even to a fully untrusted caller.

Durable defaults belong in `.reaperrc` instead of a long command line:

```toml
[commune]
roots = ["~/repos"]
allow_network = true
```

## Controlling more than one agent

- **One server, many agents.** If several sub-agents all need to read the
  same codebase, stand up one `commune --http` and point every client at it,
  rather than each agent spawning its own stdio process — the roots/hosts
  policy is enforced once, in one place, not re-implemented per agent.
- **Scope `--root` per task, not per fleet.** A supervising agent handing a
  narrower job to a sub-agent should narrow the circle to match — a sub-agent
  auditing one repo doesn't need `--root` pointed at the whole workspace.
- **Leave `--allow-write` off by default.** The write-gated tools change the
  filesystem (`reanimate`/`resurrect` write files, `banish` deletes the clone
  cache, `scavenge` fills a library directory). Turn it on only for the
  specific agent and task that needs it, never as a fleet-wide default.
- **`--allow-network` is `plague`'s alone.** Nothing else in the tool set
  ever reaches out; granting it doesn't open anything but the OSV lookup.

## Resources and prompts (skip the tool-call round trip)

Three MCP resources answer common "what's the current state" questions
without a tool call: `reaper://grimoire` (effective config + recipes),
`reaper://tombstone` (vital stats), `reaper://census` (file-type census) —
all for the server's default source.

Three ready-made prompts give an agent a sane default workflow instead of
guessing which tools to chain: `pack-this-repo`, `audit-this-repo`,
`explain-this-repo`. An orchestrating agent can hand a sub-agent one of these
prompt names instead of writing out the tool sequence itself.

## This composes with the other skills

The other `reaper-*` skills teach *which* ritual answers *which* question;
this one removes the shell between an agent and those rituals. A sub-agent
that already knows (from `reaper-audit`, say) that `exhume` finds committed
secrets doesn't need to know it's calling an MCP tool instead of a CLI
command — the tool's name, arguments, and JSON shape are the same either way.
