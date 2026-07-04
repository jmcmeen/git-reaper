---
name: reaper-orchestrate
description: Control git-reaper across many repositories or many rituals from one command — fleet manifests (necropolis.toml) to fan one ritual over a set of repos, rites to chain several rituals into one named, combined-output workflow, and recipes to save a single tuned incantation. Use when asked to run the same check across a fleet of repos, build a repeatable multi-step audit or report, orchestrate git-reaper for a set of agents or targets, or avoid re-typing the same flags every run.
---

git-reaper has three ways to save yourself from retyping an incantation, each
answering a different shape of "do this again, across that": a **recipe**
saves one command's flags, **necropolis** fans one ritual across many repos,
and a **rite** chains several rituals into one named workflow that can also
run across many repos. Picking the right one is the whole skill.

## Pick the shape

| Need | Use | Command |
| --- | --- | --- |
| One repo, one ritual, flags you don't want to retype | a recipe | `reaper cast <name>` |
| One ritual, every repo in a fleet | a manifest | `reaper necropolis <ritual> --manifest necropolis.toml` |
| Several rituals, as one named chain, over one or many repos | a rite | `reaper perform <name> [sources...]` |

They compose: a rite's steps are recipe-shaped (`command` + args), and a rite
can run against the same sources a fleet manifest lists (see below).

## Recipes: one tuned incantation, saved

```toml
# .reaperrc
[recipes.nightly-pack]
command = "conjure"
args = [".", "--sha256", "--out", "PACKED.md"]
```

```sh
reaper cast nightly-pack
reaper cast nightly-pack --split-tokens 50000   # extra args override at cast time
```

## Fleets: one ritual, every repo

```toml
# necropolis.toml
[[grave]]
source = "https://github.com/org/service-a"

[[grave]]
source = "../service-b"
tags = ["backend"]
```

```sh
reaper necropolis exhume --manifest necropolis.toml --out-dir audit/
reaper necropolis omens --tag backend --out-dir risk/   # only tagged graves
```

One artifact per grave plus a combined `INDEX.md`/`INDEX.json` in `--out-dir`.
Most source-taking rituals fan out this way; meta commands (`cast`, `summon`,
`veil`, `reanimate`, `grimoire`, `banish`, `banshee`, `leech`, `necropolis`
itself) can't, since they don't take a plain repo source the same way.

## Rites: several rituals, one named chain, combined output

A rite is an ordered list of steps — each a ritual plus its CLI args — run
in sequence against one or more sources. The literal token `{source}` in a
step's args is filled in per source at run time.

```toml
# .reaperrc
[rites.audit]
description = "the nightly sweep"

[[rites.audit.steps]]
command = "exhume"
args = ["{source}", "--fail-on", "any"]

[[rites.audit.steps]]
command = "omens"
args = ["{source}", "-n", "20"]
name = "risk"
```

```sh
reaper perform audit .                              # one repo
reaper perform audit . ../service-b ../service-c     # the same chain, three repos
reaper perform audit . --format json                 # every step's full JSON, combined
```

A step needs `--format json`/`--out` support to join a rite (most analysis
rituals qualify; `harvest`/`conjure`/`veil` and multi-argument rituals like
`scry` don't — they stay `cast`/CLI-only). A failing step is recorded, not
fatal: the rest of the chain still runs, so one bad repo or one broken step
doesn't blank out everything else. Check the exit code (nonzero if any step
failed) or, in `--format json`, each outcome's `ok`/`error`.

The combined JSON shape:

```json
{
  "rite": "audit",
  "sources": [".", "../service-b"],
  "outcomes": [
    {"step": "exhume", "command": "exhume", "source": ".", "ok": true, "output": {...}},
    {"step": "risk",   "command": "omens",  "source": ".", "ok": true, "output": {...}}
  ]
}
```

## Running a rite over a fleet manifest

`perform` takes sources as plain arguments, not a `necropolis.toml` — if the
fleet already lives in a manifest, pull the sources out and hand them to
`perform` directly:

```sh
sources=$(python3 -c '
import tomllib, sys
with open("necropolis.toml", "rb") as f:
    print(*[g["source"] for g in tomllib.load(f)["grave"]])
')
reaper perform audit $sources --format json > audit.json
```

(`examples/rite-perform.sh` in the git-reaper repo is a runnable version of
this pattern.)

## For an orchestrating agent

- A rite is the unit to hand a sub-agent when the task is "run this fixed
  sequence of checks" — the agent names it once (`reaper perform audit .`)
  instead of re-deriving which rituals to chain and in what order every time.
- Compose with `reaper-commune`: a rite composed and saved in `.reaperrc` is
  visible to `reaper grimoire` from any client of a shared `commune` server,
  so a fleet of agents can agree on "the audit rite" without each one
  re-authoring it.
- Prefer a rite over a hand-rolled shell loop of `reaper` calls when the
  output needs to be combined and machine-read afterward — a rite's
  `--format json` is one parseable document; a loop of separate invocations
  is N documents an agent has to stitch together itself.
