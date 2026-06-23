#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
STATE_DIR="${1:-${APP_DIR}/state}"
mkdir -p "${STATE_DIR}"
cp "${APP_DIR}/data/master_seed.json" "${STATE_DIR}/financial_master.json"
echo "${STATE_DIR}/financial_master.json"
