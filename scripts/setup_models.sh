#!/usr/bin/env bash
# Pull the required Ollama model into the running ollama container.
# Run this once after 'docker compose up -d'.
# Usage: scripts/setup_models.sh [model_name]
set -euo pipefail

MODEL="${1:-llama3.1}"

echo "Waiting for Ollama to be ready..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done

echo "Pulling model: $MODEL"
docker compose exec ollama ollama pull "$MODEL"
echo "Done. Model '$MODEL' is ready."
