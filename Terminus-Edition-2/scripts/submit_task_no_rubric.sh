#!/usr/bin/env bash
# Deprecated name — delegates to submit_task.sh (zip.sh + stb staging upload).
set -euo pipefail
exec bash "$(cd "$(dirname "$0")" && pwd)/submit_task.sh" "$@"
