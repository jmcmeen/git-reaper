# Library use

All real work lives in `git_reaper.core` and returns structured data
objects, never pre-formatted strings. The CLI only handles presentation and
I/O, so everything the CLI can do, your code and notebooks can do too.

## The pattern

Resolve a source, run a core function, hand the result to a formatter (or
inspect it directly):

```python
from git_reaper.core.source import resolve_source
from git_reaper.core.harvest import harvest
from git_reaper.formatters.markdown import write_harvest

repo = resolve_source("https://github.com/Textualize/rich").repo
result = harvest(repo, patterns=("*.md",))

print(result.total_lines, result.token_estimate)
for entry in result.skipped:
    print("left in the ground:", entry.path, entry.skip_reason)

with open("RICH.md", "w") as fh:
    write_harvest(result, fh)
```

Trees work the same way:

```python
from git_reaper.core.source import resolve_source
from git_reaper.core.tree import tree
from git_reaper.formatters import jsonfmt

result = tree(resolve_source(".").repo, with_sizes=True)
print(jsonfmt.render(result))
```

## Result models

Every core function returns dataclasses from `git_reaper.models`:

| Model | Returned by |
| --- | --- |
| `HarvestResult` | `core.harvest.harvest` |
| `TreeResult` | `core.tree.tree` |
| `PulseResult` | `core.pulse.pulse` |
| `BanishResult` | `cache.banish` |

Each carries a `Provenance` stamp (source, ref, sha, timestamp, tool
version, exact invocation) so artifacts stay reproducible and citable.

## JSON schemas

`git_reaper.schemas.schema_for(model)` builds a JSON schema for any result
model, mechanically derived from the dataclasses, so downstream consumers
never have to guess shapes:

```python
from git_reaper import schemas
from git_reaper.models import TreeResult

print(schemas.schema_for(TreeResult)["$id"])
```

## Determinism

Core functions accept a `generated` timestamp override; pass a fixed value
and the rendered artifact is byte-identical across runs — the property the
test suite pins down.
