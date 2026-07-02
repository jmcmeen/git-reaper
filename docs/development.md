# Development

Everything runs through `uv` and the Makefile.

```sh
make setup      # create venv, install deps
make check      # lint + typecheck + tests (the full gauntlet)
make fmt        # auto-format and fix lint findings
make test       # pytest
make cov        # pytest with coverage
make docs       # serve the docs locally with live reload
make run ARGS="tree ."
make build      # sdist + wheel
```

## Testing

The suite builds throwaway repos with real git (the fixture necropolis),
so history behavior is tested against actual git, not mocks. Every test
gets an isolated catacombs cache via `GIT_REAPER_CACHE`.

CI runs lint + mypy + the test matrix (Linux/macOS/Windows x Python
3.10-3.13) on every push and pull request, and builds the docs strictly.

## Versioning

The version is derived from git tags via `hatch-vcs` — there is no version
string to bump in the source. Between tags you get a dev version like
`0.2.0.dev3+g1a2b3c4`.

## Releasing

1. Make sure `main` is green.
2. Tag: `git tag v0.2.0 && git push --tags`
3. Create a GitHub release for the tag.

Publishing the release triggers the `publish` workflow, which runs the
tests, builds the sdist and wheel, and uploads to PyPI via trusted
publishing (OIDC — no API tokens stored in the repo).

!!! note
    Trusted publishing must be configured once on PyPI: add a publisher
    for this repo with workflow `publish.yml` and environment `pypi`.

Docs deploy to GitHub Pages automatically on every push to `main`.
