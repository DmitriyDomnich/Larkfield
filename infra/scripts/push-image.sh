#!/usr/bin/env bash
# Builds the image and pushes it to the environment's ECR repository, tagged with the commit SHA.
# Tags are immutable: an existing tag is left as it is. Writes pushed=true|false to $GITHUB_OUTPUT;
# false while the repository doesn't exist yet (the first deploy, before `terraform apply`).
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
image="${registry}/${repository}:${IMAGE_TAG:?}"
if aws ecr describe-images --repository-name "$repository" --image-ids "imageTag=${IMAGE_TAG}" > /dev/null 2> "$errors"; then
  echo "${image} already pushed"
elif ! grep -q ImageNotFoundException "$errors"; then
  cat "$errors" >&2
  exit 1
else
  aws ecr get-login-password | docker login --username AWS --password-stdin "$registry"
  docker build --tag "$image" .
  docker push "$image"
fi
echo "pushed=true" >> "${GITHUB_OUTPUT:-/dev/null}"
