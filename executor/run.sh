#!/usr/bin/env bash
# Runs untrusted code in an isolated Docker container.
# Usage: ./run.sh "<python_code>" [timeout_seconds]
#
# Resource limits: 50MB RAM, 0.5 CPU, no network, 10s wall-clock timeout.
# The container is auto-removed after execution (--rm).

set -euo pipefail

CODE="${1:?Usage: run.sh '<code>' [timeout]}"
TIMEOUT="${2:-10}"

docker run \
  --rm \
  --network none \
  --memory 50m \
  --cpus 0.5 \
  --read-only \
  --tmpfs /tmp:size=10m \
  --user 1000:1000 \
  --ulimit nproc=64 \
  --stop-timeout "$TIMEOUT" \
  cs455-executor \
  "$CODE"
