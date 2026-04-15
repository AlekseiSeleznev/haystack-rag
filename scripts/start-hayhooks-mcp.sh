#!/usr/bin/env bash
set -euo pipefail

exec hayhooks mcp run \
  --host 0.0.0.0 \
  --port 1417 \
  --pipelines-dir /app/config/pipelines \
  --additional-python-path /app/src \
  --json-response
