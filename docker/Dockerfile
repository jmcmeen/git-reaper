# git-reaper as a container: the CLI plus the `commune` MCP server.
#
# By default this installs the released wheel from PyPI. To build from a
# branch instead:
#
#   docker build --build-arg \
#     REAPER_SPEC="git-reaper[mcp] @ git+https://github.com/jmcmeen/git-reaper" .

FROM python:3.12-slim

# The reaper needs real git for everything history-shaped.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ARG REAPER_SPEC="git-reaper[mcp]"
RUN pip install --no-cache-dir "${REAPER_SPEC}"

# Mounted repos are owned by the host user, not the container user; without
# this, git refuses them as "dubious ownership" and every ritual fails.
RUN git config --system safe.directory '*'

# An unprivileged soul to run as. The catacombs (clone cache) live in its home.
RUN useradd --create-home reaper
USER reaper
ENV HOME=/home/reaper

# The graves to reap: mount your repositories here (read-only is fine).
VOLUME /repos
WORKDIR /repos

EXPOSE 6666

# MCP protocol traffic only flows once a client connects, so health is
# "the port answers", checked without any extra tooling in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 6666), 2)"

# Read-only MCP server over HTTP, rooted to the mounted repos.
# Override the command for one-off CLI runs (see docker-compose.yml).
CMD ["reaper", "commune", "/repos", "--http", "0.0.0.0:6666", "--root", "/repos"]
