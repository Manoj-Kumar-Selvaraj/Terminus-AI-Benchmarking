#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-/app}"

install -m 0644 "${SCRIPT_DIR}/module.go" "${APP_DIR}/infra/modules/ec2/module.go"
gofmt -w "${APP_DIR}/infra/modules/ec2/module.go"
(cd "${APP_DIR}" && go build ./cmd/ec2sim)
