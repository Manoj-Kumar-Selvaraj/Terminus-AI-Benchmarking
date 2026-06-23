#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/edge_proxy_deploy.py.m4" /app/tools/edge_proxy_deploy.py
chmod +x /app/tools/edge_proxy_deploy.py
python3 -m py_compile /app/tools/edge_proxy_deploy.py
