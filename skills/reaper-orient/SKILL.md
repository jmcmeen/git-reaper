---
name: reaper-orient
description: Map an unfamiliar repository fast with git-reaper — folder layout, size, languages, code structure, and vital stats. Use when asked to explore, understand, summarize, or get oriented in a codebase before working in it.
---

git-reaper (`reaper` on PATH; `pip install git-reaper` or `uv tool install
git-reaper` if missing) reaps structured facts from a repo so you don't have
to walk it file by file. Every command takes a local path **or a remote URL**
(remote sources are cloned to a cache automatically) and prints the artifact
to stdout — narration goes to stderr, so piping is always safe.

## The orientation sequence

```sh
reaper limbs .  --format json     # folder layout, limb by limb
reaper census . --format json     # counts, sizes, languages, token estimate
reaper bones .  -o MAP.md         # imports, signatures, docstrings — no bodies
reaper tombstone .                # vital stats card (born, age, commits, souls)
```

`limbs` is the fastest way to learn a layout: a hierarchical tree honoring
`.gitignore`, with `--depth N` to cap it, `--dirs-only` for the skeleton,
`--sizes` / `--lines` for weight, and `--exclude GLOB` to skip noise. Prefer
`--format json` and read `file_count` / the nested tree instead of parsing
markdown.

`census` answers "how big is this really" — per-language file counts, sizes,
line counts, and a token estimate, so you know whether the repo fits in
context before reading it.

`bones` is the structural map: every file's imports, signatures, and
docstrings with the implementations stripped. Python works out of the box;
other languages need `pip install "git-reaper[bones]"`.

## Filling in specifics

| Question | Command |
| --- | --- |
| Where are the TODOs and how old are they? | `reaper unfinished . --age` |
| What does the docs corpus say? | `reaper harvest . --pattern "*.md" -o DOCS.md` |
| Which files churn the most (bug-risk proxy)? | `reaper haunt . -n 20 --format json` |
| Duplicate files wasting space? | `reaper doppelgangers .` |
| What is heaviest, tree and history? | `reaper bloat .` |

## Ground rules

- Add `--format json` to any analysis command for machine-readable output;
  `--schema` prints the exact JSON schema and exits.
- Every JSON artifact carries a `provenance` block (source, ref/sha,
  invocation) — cite it when reporting findings.
- Output is deterministic: same repo state + same flags = same artifact.
- Remote example: `reaper limbs https://github.com/owner/repo --format json`
  works identically; add `--ref TAG` for a specific ref.
