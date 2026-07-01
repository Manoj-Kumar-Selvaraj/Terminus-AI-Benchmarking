#!/usr/bin/env bash
set -Eeuo pipefail
MOD="/app/modules/private_egress"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$MOD"
cp -f "${SCRIPT_DIR}/module/"*.tf "$MOD/"
terraform fmt -recursive "$MOD" >/dev/null