#!/bin/bash
set -euo pipefail
cd /app
exec /app/build/payment-api "$@"
