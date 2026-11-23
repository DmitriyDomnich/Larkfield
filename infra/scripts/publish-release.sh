#!/usr/bin/env bash
# Makes releases/<sha>/ of the site bucket the live site and invalidates CloudFront. Copies every
# object over live/ first: an S3-to-S3 sync skips a same-size file whose copy in live/ is newer,
# which is every file when going back to an older release. Then removes what the release lacks.
#
# env: SITE_BUCKET, DISTRIBUTION_ID; argument: the release's commit SHA
set -euo pipefail

release="s3://${SITE_BUCKET:?}/releases/${1:?}"
live="s3://${SITE_BUCKET}/live"
aws s3 cp "$release" "$live" --recursive --only-show-errors
aws s3 sync "$release" "$live" --delete --only-show-errors
aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID:?}" --paths "/*" > /dev/null
echo "live: ${1}"
