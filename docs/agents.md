# Agents, Docker, and examples

Three ready-made ways to put the reaper to work beyond your own terminal,
each living in its own folder at the repo root.

## Docker: a containerized reaper and MCP server

[`docker/`](https://github.com/jmcmeen/git-reaper/tree/main/docker) holds a
`Dockerfile` and `docker-compose.yml` that run the CLI and the `commune` MCP
server in a container:

```sh
cd docker
mkdir -p repos                        # or: export REAPER_REPOS=~/repos
docker compose up -d reaper-mcp       # MCP server on http://localhost:6666/mcp
docker compose run --rm reaper tombstone /repos/some-repo   # one-off CLI
```

Every read-only ritual becomes an agent-callable MCP tool, rooted to the
mounted `/repos` and returning the same provenance-stamped JSON the CLI
prints. The compose file binds to loopback and ships with all guardrails
engaged; `--host`, `--allow-network`, and `--allow-write` loosen them
deliberately. `docker/README.md` covers stdio transport (no port at all) and
connecting clients such as Claude Code.

## Agent Skills: teach an agent the rituals

[`skills/`](https://github.com/jmcmeen/git-reaper/tree/main/skills) ships
four portable Agent Skills — folders with a `SKILL.md` any skill-aware agent
can consume:

| Skill | Teaches the agent to |
| --- | --- |
| `reaper-orient` | Map an unfamiliar repo: `limbs`, `census`, `bones`, `tombstone`. |
| `reaper-necromancy` | Mine history for who/when/why: `chronicle`, `souls`, `autopsy`, `lineage`, `possession`, `scry`, and friends. |
| `reaper-audit` | Audit and gate: `exhume`, `omens`, `plague`, `veil`, `ward`. |
| `reaper-pack` | Pack repos for LLM context and back: `conjure`, `reanimate`, `harvest`, `leech`, `embalm`. |

Install by copying a folder into your agent's skills directory (for Claude
Code: `.claude/skills/` per project or `~/.claude/skills/` globally). Skills
and the MCP server compose well: the skills say *which* ritual answers
*which* question; `commune` removes the shell. And `reaper distill` goes the
other direction — it generates a repo-specific skill *from* a codebase.

## Examples: scripted end-to-end workflows

[`examples/`](https://github.com/jmcmeen/git-reaper/tree/main/examples) holds
runnable bash scripts that chain rituals into complete workflows:

| Script | The workflow |
| --- | --- |
| `orientation.sh` | First contact with an unfamiliar repo: layout, size, code map, vital stats, contributors, TODO debt — one report directory. |
| `audit.sh` | The audit sweep: secrets, risk, dependency advisories, debt. Exits 3 if a gate breaks. |
| `pack-roundtrip.sh` | Pack with hashes, raise the tree elsewhere with `--verify`, byte-compare every risen file. |
| `ci-gate.sh` | The one-line repo-health gate: `reaper ward`, exit 3 on a broken ward. |
| `fleet.sh` | Fan a ritual across a `necropolis.toml` fleet, one artifact per repo plus an index. |

Each defaults to the current directory, accepts a path or remote URL, and
honors `REAPER="uv run reaper"` for running from a source checkout.
