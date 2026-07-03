---
name: reaper-audit
description: Audit a repository with git-reaper — committed secrets across full history, per-file risk scores, dependency advisories, history-bloat purge plans, and a one-command CI gate. Use when asked to scan for leaked secrets or API keys, assess code risk, check dependencies for vulnerabilities, redact sensitive output, or wire a repo-health gate into CI.
---

git-reaper (`reaper` on PATH; `pip install git-reaper` if missing) bundles
the audit rituals behind one CLI. All of them take a local path or remote
URL, print to stdout (narration to stderr), and support `--format json` +
`--schema`. The gating commands exit **3** when the gate breaks — wire that
straight into CI.

## The audit sweep

```sh
reaper exhume . --format json          # secrets across the FULL history
reaper omens .  -n 20 --format json    # riskiest files (churn+bugs+age+size)
reaper plague . --offline              # dependency manifests, no network
reaper unfinished . --age              # TODO/FIXME debt and its age
```

- `exhume` scans every commit, not just the working tree, via regex
  signatures plus an entropy sweep (`--no-entropy` for signatures only).
  Findings report commit, path, rule, and a **masked** preview — the full
  secret is never printed. `--baseline known.json` suppresses accepted
  findings.
- `plague` is the only command that ever touches the network, and only when
  the run allows it: use `--offline` unless the user has opted into querying
  the OSV database.
- `omens` blends churn, bug-fix density, recency, and size into one 0..1
  score per file. Hints, not fate — use it to rank review effort.

## Gating (exit code 3)

```sh
reaper exhume . --fail-on any       # any committed secret fails the build
reaper omens .  --fail-over 0.85    # any file scoring ≥ 0.85 fails
reaper plague . --fail-on any       # any known advisory fails
reaper ward .                       # the composite gate: one command, one policy
```

`ward` reads a `[ward]` policy from `.reaperrc` (or `[tool.reaper]` in
pyproject.toml) and folds the exhume/omens/plague/rot thresholds into a
single pass/fail; with nothing configured it gates committed secrets. Prefer
one `reaper ward` in CI over four separate gates.

## Redaction and cleanup

- `reaper veil FILE` (or `-` for stdin) scrubs secrets and configured
  patterns from any text before it leaves the machine, replacing each match
  with `[VEILED:rule-name]`. Packing a repo for an LLM? Use
  `reaper conjure . --veil` to scrub in flight.
- `reaper exorcise . --min-size 5MB` composes exhume's findings and the dead
  blobs still weighing down `.git` into a printed `git filter-repo`/BFG purge
  plan. It **plans only** — it never rewrites history itself, and neither
  should you without explicit sign-off.

## Reporting

Findings deserve provenance: every JSON artifact carries a `provenance` block
(source, sha, exact invocation). Report secrets by commit + path + rule with
the masked preview — never attempt to recover or print the full secret.
