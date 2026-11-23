#!/usr/bin/env bash
# Writes the variables a pipeline `terraform plan/apply` of one environment root needs, in the
# current directory (the root):
#   ci.auto.tfvars.json        the environment's tfvars, from its TFVARS variable
#   pipeline.auto.tfvars.json  runtime_enabled (SSM), restore_db_snapshot (snapshot exists), EXTRA_VARS
# and runtime_enabled to $GITHUB_OUTPUT.
#
# env: ENVIRONMENT (dev | prod), TFVARS (JSON), EXTRA_VARS (JSON object, optional)
set -euo pipefail

prefix="larkfield-${ENVIRONMENT:?}"
printf '%s' "${TFVARS:?}" | jq . > ci.auto.tfvars.json

if ! runtime_enabled=$(aws ssm get-parameter --name "/${prefix}/runtime_enabled" \
  --query Parameter.Value --output text 2> ssm-error.txt); then
  if grep -q ParameterNotFound ssm-error.txt; then
    runtime_enabled=false # never started
  else
    cat ssm-error.txt >&2
    exit 1
  fi
fi
rm -f ssm-error.txt

# an error other than "not found" must fail: on Start it would create an empty database
if aws rds describe-db-snapshots --db-snapshot-identifier "${prefix}-latest" > /dev/null 2> rds-error.txt; then
  restore_db_snapshot=true
elif grep -q DBSnapshotNotFound rds-error.txt; then
  restore_db_snapshot=false
else
  cat rds-error.txt >&2
  exit 1
fi
rm -f rds-error.txt

extra_vars="${EXTRA_VARS:-}"
jq -n \
  --argjson runtime_enabled "$runtime_enabled" \
  --argjson restore_db_snapshot "$restore_db_snapshot" \
  --argjson extra "${extra_vars:-null}" \
  '{runtime_enabled: $runtime_enabled, restore_db_snapshot: $restore_db_snapshot} + ($extra // {})' \
  > pipeline.auto.tfvars.json

echo "runtime_enabled=${runtime_enabled}" >> "${GITHUB_OUTPUT:-/dev/null}"
echo "${ENVIRONMENT}: runtime_enabled=${runtime_enabled}, restore_db_snapshot=${restore_db_snapshot}"
