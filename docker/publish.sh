#!/usr/bin/env bash
# Builds both images for amd64 and arm64 servers and pushes them to the registry (public once pushed).
#
#   docker login ghcr.io                      (once, with a GitHub token that may write packages)
#   docker/make-public-data.sh                (when the Bible data should be refreshed)
#   docker/publish.sh [tag]                   (tag: latest when not given)

set -euo pipefail

repository="$(cd "$(dirname "$0")/.." && pwd)"
registry="${IMAGE_REGISTRY:-ghcr.io/paulcarrick}"
tag="${1:-latest}"

if [ ! -f "$repository/docker/public-data/bible-data.sql.gz" ]; then
  echo "No docker/public-data/bible-data.sql.gz: run docker/make-public-data.sh first." >&2
  exit 1
fi

docker buildx inspect bible-and-beyond-builder > /dev/null 2>&1 \
  || docker buildx create --name bible-and-beyond-builder --driver docker-container > /dev/null

for image in database web; do
  echo "Building and pushing $registry/bible-and-beyond-$image:$tag ..."
  docker buildx build --builder bible-and-beyond-builder \
    --platform linux/amd64,linux/arm64 \
    --file "$repository/docker/$image/Dockerfile" \
    --tag "$registry/bible-and-beyond-$image:$tag" \
    --push "$repository"
done
echo "Published. Installers get them with: docker compose -f docker/compose.yml pull"
