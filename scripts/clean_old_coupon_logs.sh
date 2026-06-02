#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/var/log/isyone/coupons"

if [ ! -d "$LOG_DIR" ]; then
  echo "Diretório não encontrado: $LOG_DIR"
  exit 0
fi

find "$LOG_DIR" -type f -mtime +30 -name '*.log' -delete
echo "Logs antigos removidos."
