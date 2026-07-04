# Agent Skills for git-reaper

Portable [Agent Skills](https://code.claude.com/docs/en/skills) that teach a
coding agent to wield git-reaper. Each skill is a folder holding a `SKILL.md`
with YAML frontmatter (`name`, `description`) — the description is what the
agent matches against when deciding a skill applies, and the body is loaded
only then.

| Skill | Teaches the agent to |
| --- | --- |
| [reaper-orient](reaper-orient/SKILL.md) | Map an unfamiliar repo: `limbs` for the folder layout, `census` for size and languages, `bones` for the structural code map, `tombstone` for vital stats. |
| [reaper-necromancy](reaper-necromancy/SKILL.md) | Mine history for who/when/why: `chronicle`, `souls`, `autopsy`, `lineage`, `possession`, `scry`, `graveyard`/`resurrect`, and friends. |
| [reaper-audit](reaper-audit/SKILL.md) | Audit and gate: `exhume` for committed secrets, `omens` for risk, `plague` for dependency advisories, `veil` for redaction, `ward` for the one-command CI gate. |
| [reaper-pack](reaper-pack/SKILL.md) | Pack repos for LLM context and back: `conjure` (sharding, hashes, veiling), `reanimate`, `harvest`, `leech`, `embalm`. |
| [reaper-commune](reaper-commune/SKILL.md) | Give an agent (or a fleet of them) controlled access to a repo over MCP: `reaper commune`'s stdio/HTTP transports, the `--root`/`--host`/`--allow-write`/`--allow-network` guardrails, and its resources and prompts. |
| [reaper-orchestrate](reaper-orchestrate/SKILL.md) | Control git-reaper across many repos or many rituals from one command: recipes (`cast`) for one saved incantation, fleet manifests (`necropolis`) to fan one ritual over many repos, and rites (`perform`) to chain several rituals into one named, combined-output workflow. |

## Installing

Copy a skill folder wherever your agent looks for skills. For Claude Code:

```sh
# one project
cp -r skills/reaper-orient .claude/skills/

# everywhere
cp -r skills/reaper-* ~/.claude/skills/
```

Other agent frameworks that support the SKILL.md convention can consume the
folders unchanged. The skills assume `reaper` is on PATH
(`pip install git-reaper` or `uv tool install git-reaper`).

## One other way to hand git-reaper to an agent

**`reaper distill`** goes the other direction from every skill above: it
generates a *new*, repo-specific skill from any codebase (conventions, real
build commands, hotspots), rather than teaching the agent about git-reaper
itself.

(For MCP instead of CLI incantations, see the `reaper-commune` skill above —
skills and MCP compose well: the skills explain *which* ritual answers
*which* question; commune removes the shell. [docker/](../docker/README.md)
has a ready-made compose setup.)
