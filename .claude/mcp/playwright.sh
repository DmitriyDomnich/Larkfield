#!/bin/sh
# Playwright MCP server for /e2e: an isolated in-memory browser profile limited to the local app,
# the local API, Cognito and the documents bucket. Origins come from frontend/.env, so no URLs are
# committed. Sessions are loaded per user with browser_set_storage_state (--caps=storage).
set -eu
cd "$(dirname "$0")/../.."
set -a
. frontend/.env
set +a

origins="http://localhost:3000;$NEXT_PUBLIC_API_URL;https://cognito-idp.$NEXT_PUBLIC_COGNITO_REGION.amazonaws.com;$NEXT_PUBLIC_DOCUMENTS_ORIGIN"

exec npx -y @playwright/mcp@0.0.84 \
  --isolated \
  --caps=storage \
  --allowed-origins="$origins" \
  --output-dir=build/e2e/output
