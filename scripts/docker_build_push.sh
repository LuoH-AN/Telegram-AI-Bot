#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   DOCKER_USERNAME=enltlh DOCKER_PASSWORD=*** ./scripts/docker_build_push.sh enltlh/gemen latest
#   ./scripts/docker_build_push.sh enltlh/gemen latest --no-push

IMAGE_NAME="${1:-enltlh/gemen}"
IMAGE_TAG="${2:-latest}"
PUSH_MODE="${3:-}"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker command not found. Please install Docker first."
  exit 1
fi

if [[ -n "${DOCKER_PASSWORD:-}" ]]; then
  DOCKER_USERNAME="${DOCKER_USERNAME:-enltlh}"
  echo "${DOCKER_PASSWORD}" | docker login -u "${DOCKER_USERNAME}" --password-stdin
else
  echo "Warning: DOCKER_PASSWORD is empty, skip docker login."
fi

echo "Building image: ${FULL_IMAGE}"
docker build -t "${FULL_IMAGE}" .

if [[ "${PUSH_MODE}" == "--no-push" ]]; then
  echo "Build completed. Push skipped (--no-push)."
  exit 0
fi

echo "Pushing image: ${FULL_IMAGE}"
docker push "${FULL_IMAGE}"

echo "Done: ${FULL_IMAGE}"
