#!/usr/bin/env bash
set -euo pipefail

if command -v docker compose >/dev/null 2>&1; then
  docker compose restart
else
  docker restart $(docker ps -q)
fi
