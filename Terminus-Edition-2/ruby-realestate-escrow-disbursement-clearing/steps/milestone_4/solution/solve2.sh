#!/usr/bin/env bash
set -Eeuo pipefail
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/reconcile.rb" /app/app/reconcile.rb
