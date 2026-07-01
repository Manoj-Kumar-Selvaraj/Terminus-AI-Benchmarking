#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${APP_DIR}/cmd/vpcrecover" "${APP_DIR}/bin"
cp "${SCRIPT_DIR}/recover2.go" "${APP_DIR}/cmd/vpcrecover/main.go"
/usr/local/go/bin/gofmt -w "${APP_DIR}/cmd/vpcrecover/main.go"
(cd "${APP_DIR}" && /usr/local/go/bin/go build -o "${APP_DIR}/bin/vpc-recover" ./cmd/vpcrecover)
