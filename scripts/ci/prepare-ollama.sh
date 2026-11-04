#!/usr/bin/env bash
# Install Ollama on a GitHub runner, listen on all interfaces, pull the embedding model.
set -euo pipefail
curl -fsSL https://ollama.com/install.sh | sh
OLLAMA_HOST=0.0.0.0 nohup ollama serve >/tmp/ollama.log 2>&1 &
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 2; done
ollama pull nomic-embed-text
