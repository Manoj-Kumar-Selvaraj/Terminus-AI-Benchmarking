#!/usr/bin/env bash
set -Eeuo pipefail
MOD="${APP_ROOT:-/app}/terraform/modules/secure-vnet"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$MOD"
cp -f "${SCRIPT_DIR}/module/"*.tf "$MOD/"
