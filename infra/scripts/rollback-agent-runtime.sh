#!/usr/bin/env bash
# Puts the review agent's AgentCore runtime back on the configuration "record the live release"
# saved with `get-agent-runtime`, then waits until it is READY. An update replaces the whole
# configuration, so everything saved is sent again, not only the image.
#
# usage: rollback-agent-runtime.sh <saved get-agent-runtime JSON>
# env:   POLL_SECONDS (default 10), POLL_LIMIT (default 60)
set -euo pipefail

saved="${1:?usage: rollback-agent-runtime.sh <saved get-agent-runtime JSON>}"
runtime_id=$(jq -re .agentRuntimeId "$saved")
image=$(jq -re .agentRuntimeArtifact.containerConfiguration.containerUri "$saved")

update_input=$(jq -c '
  {
    agentRuntimeId,
    agentRuntimeArtifact,
    roleArn,
    networkConfiguration,
    protocolConfiguration,
    lifecycleConfiguration,
    environmentVariables,
    platformVersion,
    description
  } | with_entries(select(.value != null))' "$saved")

echo "AgentCore runtime ${runtime_id}: back to ${image##*/}"
aws bedrock-agentcore-control update-agent-runtime --cli-input-json "$update_input" > /dev/null

for _ in $(seq "${POLL_LIMIT:-60}"); do
  status=$(aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$runtime_id" \
    --query status --output text)
  case "$status" in
    READY) echo "AgentCore runtime ${runtime_id} READY"; exit 0 ;;
    *FAILED) echo "::error::AgentCore runtime ${runtime_id} ${status}" >&2; exit 1 ;;
  esac
  sleep "${POLL_SECONDS:-10}"
done
echo "::error::AgentCore runtime ${runtime_id} not READY after the rollback" >&2
exit 1
