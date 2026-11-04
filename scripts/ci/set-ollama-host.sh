#!/usr/bin/env bash
# Point the ci overlay at the runner: the kind docker network gateway is the host seen from pods.
set -euo pipefail
OVERLAY="${1:?usage: set-ollama-host.sh <overlay-dir>}"
GW="$(docker network inspect kind -f '{{(index .IPAM.Config 0).Gateway}}')"
sed -i "s/OLLAMA_HOST_PLACEHOLDER/${GW}/g" "$OVERLAY/kustomization.yaml"
echo "ollama host for pods: $GW"
