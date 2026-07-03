# Examples

Scripted end-to-end workflows: each is a runnable bash script that chains
git-reaper rituals into something you would actually do, commented enough to
crib from. They all default to the current directory and accept a path **or a
remote URL** as the source.

| Script | The workflow |
| --- | --- |
| [orientation.sh](orientation.sh) | First contact with an unfamiliar repo: layout (`limbs`), size (`census`), code map (`bones`), vital stats (`tombstone`), contributors (`souls`), and the TODO debt (`unfinished`) into one report directory. |
| [audit.sh](audit.sh) | The audit sweep: `exhume` for committed secrets (gating), `omens` for risk, `plague` for dependency advisories, `unfinished` and `revenant` for debt. Exits 3 if a gate breaks — CI-ready. |
| [pack-roundtrip.sh](pack-roundtrip.sh) | Pack and prove it: `census` to size, `conjure --sha256` to pack, `reanimate --verify` to raise the tree elsewhere, then byte-compare every risen file. |
| [ci-gate.sh](ci-gate.sh) | The one-line repo-health gate: `reaper ward` runs the whole `[ward]` policy and exits 3 when any check breaks. |
| [fleet.sh](fleet.sh) | Fleet reaping: write a `necropolis.toml` manifest and fan a ritual across every grave, one artifact per repo plus a combined index. |

## Running them

```sh
cd examples
./orientation.sh                                # this repo
./orientation.sh https://github.com/Textualize/rich rich-report
./audit.sh . audit-report                       # exit 3 = a gate broke
./pack-roundtrip.sh ..                          # pack the parent, verify the rise
./ci-gate.sh .
./fleet.sh fleet-report . ../some-other-repo
```

All scripts need `reaper` on PATH (`pip install git-reaper` or
`uv tool install git-reaper`). Running from a source checkout instead, point
them at the venv:

```sh
REAPER="uv run reaper" ./orientation.sh ..
```

## Conventions the scripts lean on

- **stdout is the artifact, stderr is narration** — every redirect in these
  scripts is safe by construction.
- **Gates exit 3.** `exhume --fail-on`, `omens --fail-over`,
  `plague --fail-on`, and `ward` all signal a broken gate with exit code 3,
  so one `if`/`||` is a complete CI integration.
- **Determinism.** Same repo state + same flags = byte-identical artifact,
  which is what makes the pack-roundtrip comparison meaningful.
- **Remote sources just work.** Anything that takes a path takes a URL;
  clones land in `~/.cache/git-reaper/catacombs/` and are reused.
