#!/usr/bin/env bash
# PostToolUse hook: after Claude edits a Python file, lint/format it and run the unit tests.
# Exit 2 sends stderr back to Claude so it fixes the problem before moving on.
set -uo pipefail

file=$(jq -r '.tool_input.file_path // empty')
[[ "$file" == *.py ]] || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
export PATH="$HOME/.local/bin:$PATH"

if ! out=$(uv run --quiet ruff check --fix "$file" 2>&1 && uv run --quiet ruff format --quiet "$file" 2>&1); then
  printf 'ruff failed for %s:\n%s\n' "$file" "$out" >&2
  exit 2
fi

if ! out=$(uv run --quiet pytest -q -x -m "not integration" --no-header -p no:cacheprovider 2>&1); then
  printf 'Unit tests failed after editing %s:\n%s\n' "$file" "$(tail -n 40 <<<"$out")" >&2
  exit 2
fi
exit 0
