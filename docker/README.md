# git-reaper in Docker

A containerized reaper: the CLI plus the `commune` MCP server, so agents can
call the rituals without installing anything on the host beyond Docker.

## Quick start

```sh
cd docker
mkdir -p repos                       # or: export REAPER_REPOS=~/repos
docker compose up -d reaper-mcp
```

The MCP server now listens on `http://localhost:6666/mcp` (streamable HTTP),
rooted to the mounted `/repos` directory. Every read-only ritual — `limbs`,
`census`, `bones`, `chronicle`, `souls`, `haunt`, `exhume`, `omens`, and the
rest — is an agent-callable tool returning the same provenance-stamped JSON
the CLI prints.

Connect a client:

```sh
# Claude Code
claude mcp add --transport http reaper http://localhost:6666/mcp

# or in any MCP client config
{ "url": "http://localhost:6666/mcp" }
```

## One-off CLI runs

The same image runs the CLI directly; the `reaper` service (behind the `cli`
profile) mounts the same repos:

```sh
docker compose run --rm reaper tombstone /repos/some-repo
docker compose run --rm reaper census /repos/some-repo --format json
docker compose run --rm reaper conjure /repos/some-repo --sha256 > PACKED.md
```

Artifacts go to stdout and narration to stderr, so redirecting is always safe.

## stdio transport (no port at all)

MCP clients that spawn their servers can run the container over stdio instead
of HTTP — one container per session, nothing listening:

```sh
claude mcp add reaper -- docker run -i --rm \
  -v "$HOME/repos:/repos:ro" git-reaper \
  reaper commune /repos --root /repos
```

(Build the image first: `docker compose build`, or
`docker build -t git-reaper .` from this directory.)

## Widening the circle

The server ships locked down: read-only tools, no network, only `/repos`
reapable. Each guardrail loosens explicitly — edit the `command:` in
`docker-compose.yml`:

| Flag | What it allows |
| --- | --- |
| `--root PATH` | Reap local paths under `PATH` (repeatable). |
| `--host github.com` | Clone and reap repos from a remote host (repeatable). Clones persist in the `catacombs` volume. |
| `--allow-network` | Let `plague` consult the OSV database (otherwise it parses manifests offline). |
| `--allow-write` | Expose the writing rituals: `resurrect`, `reanimate`, `banish`. Drop the `:ro` on the volume mount too, or they will have nowhere to write. |

Shared defaults can live in a `.reaperrc` instead — see the `[commune]`
section in the top-level README.

## Notes

- **No auth.** The compose file binds the port to `127.0.0.1` on purpose. To
  share one reaper with a team, put a reverse proxy (with TLS and auth) in
  front before exposing it.
- **Dubious ownership.** Mounted repos belong to your host user, not the
  container's; the image sets `git config --system safe.directory '*'` so git
  reads them anyway. That is fine for an analysis container; do not copy that
  line into images that also run untrusted code.
- **Building from source.** The image installs the released wheel from PyPI.
  `--build-arg REAPER_SPEC="git-reaper[mcp] @ git+https://github.com/jmcmeen/git-reaper"`
  builds from the repo instead.
