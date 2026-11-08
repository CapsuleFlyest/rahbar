#!/usr/bin/env bash
# Run Ollama in a container on the runner (reachable from kind pods via the docker gateway),
# then pull the embedding model. Retries because registries are sometimes flaky.
set -euo pipefail
docker run -d --name ollama -p 11434:11434 ollama/ollama
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 2; done
for attempt in 1 2 3 4 5; do
  docker exec ollama ollama pull nomic-embed-text && exit 0
  echo "pull failed (attempt $attempt), retrying"; sleep 10
done
exit 1
