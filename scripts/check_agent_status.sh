#!/usr/bin/env bash
set -euo pipefail

systemctl status isy-agent --no-pager || docker ps | grep -i isy || true
