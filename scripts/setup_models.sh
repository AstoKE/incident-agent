#!/usr/bin/env bash
# Pull the required Ollama models (chat + embedding) into the running ollama container.
# Run this once after 'docker compose up -d'.
# Usage: scripts/setup_models.sh [chat_model] [embed_model]
set -euo pipefail

MODEL="${1:-qwen3.5:9b}"
EMBED_MODEL="${2:-qwen3-embedding:0.6b}"

echo "Waiting for Ollama to be ready..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done

for m in "$MODEL" "$EMBED_MODEL"; do
  echo "Pulling model: $m"
  docker compose exec ollama ollama pull "$m"
done
echo "Done. Models '$MODEL' and '$EMBED_MODEL' are ready."
