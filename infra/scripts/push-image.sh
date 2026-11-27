#!/usr/bin/env bash
# Builds the two arm64 images and pushes them to the environment's ECR repository:
# target `app` as <sha> (API, workers, migration) and target `agent-runtime` as <sha>-agent-runtime
# (Bedrock AgentCore Runtime). Tags are immutable: an existing tag is left as it is. Writes
# pushed=true|false to $GITHUB_OUTPUT; false while the repository doesn't exist yet (the first
# deploy, before `terraform apply`).
#
# env: ENVIRONMENT (dev | prod), IMAGE_TAG, AWS_REGION
set -euo pipefail

repository="larkfield-${ENVIRONMENT:?}"
errors=$(mktemp)
if ! aws ecr describe-repositories --repository-names "$repository" > /dev/null 2> "$errors"; then
  if grep -q RepositoryNotFoundException "$errors"; then
    echo "pushed=false" >> "${GITHUB_OUTPUT:-/dev/null}"
    echo "no repository ${repository} yet"
    exit 0
  fi
  cat "$errors" >&2
  exit 1
fi

registry="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.${AWS_REGION:?}.amazonaws.com"
logged_in=false

push_target() {
  local target="$1" tag="$2"
  local image="${registry}/${repository}:${tag}"
  if aws ecr describe-images --repository-name "$repository" --image-ids "imageTag=${tag}" > /dev/null 2> "$errors"; then
    echo "${image} already pushed"
    return
  fi
  if ! grep -q ImageNotFoundException "$errors"; then
    cat "$errors" >&2
    exit 1
  fi
  if [ "$logged_in" = false ]; then
    aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"
    logged_in=true
  fi
  docker build --platform linux/arm64 --target "$target" --tag "$image" .
  docker push "$image"
}

push_target app "${IMAGE_TAG:?}"
push_target agent-runtime "${IMAGE_TAG}-agent-runtime"
echo "pushed=true" >> "${GITHUB_OUTPUT:-/dev/null}"
