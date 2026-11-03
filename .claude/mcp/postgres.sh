#!/bin/sh
# Read-only Postgres MCP server for Claude Code, run in Docker.
# Killing `docker run` doesn't stop the container, so each container is labelled with the PID of
# the script that started it: containers whose script is gone (a killed session) are removed
# before a new one starts, and the script removes its own container when it is stopped.
set -eu
cd "$(dirname "$0")/../.."
set -a
. ./.env
set +a

for c in $(docker ps -aq --filter label=larkfield.mcp=postgres); do
  pid=$(docker inspect -f '{{index .Config.Labels "larkfield.mcp.pid"}}' "$c")
  kill -0 "$pid" 2>/dev/null || docker rm -f "$c" >/dev/null
done

cid=$(docker create -i --rm --label larkfield.mcp=postgres --label "larkfield.mcp.pid=$$" \
  -e DATABASE_URI="$DATABASE_URL" crystaldba/postgres-mcp:0.3.0 --access-mode=restricted)
trap 'docker rm -f "$cid" >/dev/null 2>&1' EXIT
trap 'exit 143' INT TERM HUP
# In the background so a signal interrupts `wait` and runs the trap; <&0 keeps Claude Code's stdin
docker start -ai "$cid" <&0 &
wait $!
