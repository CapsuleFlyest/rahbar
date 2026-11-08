#!/usr/bin/env bash
# Point the ci overlay at the runner: the kind docker network's IPv4 gateway is the host seen from pods.
set -euo pipefail
OVERLAY="${1:?usage: set-ollama-host.sh <overlay-dir>}"
GW="$(docker network inspect kind -f '{{range .IPAM.Config}}{{.Gateway}}{{"\n"}}{{end}}' \
  | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -1)"
[ -n "$GW" ] || { echo "no IPv4 gateway found on the kind network" >&2; docker network inspect kind >&2; exit 1; }
sed -i "s/OLLAMA_HOST_PLACEHOLDER/${GW}/g" "$OVERLAY/kustomization.yaml"
echo "ollama host for pods: $GW"
