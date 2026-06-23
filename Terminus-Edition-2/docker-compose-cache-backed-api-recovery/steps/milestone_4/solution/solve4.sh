#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose_api_recovery.py.m4" /app/tools/compose_api_recovery.py
chmod +x /app/tools/compose_api_recovery.py
python3 -m py_compile /app/tools/compose_api_recovery.py
