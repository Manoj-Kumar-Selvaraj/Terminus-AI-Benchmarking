#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
cp /steps/milestone_5/solution/module.go "${APP_DIR}/infra/modules/ec2/module.go"
gofmt -w "${APP_DIR}/infra/modules/ec2/module.go"
(cd "${APP_DIR}" && go build ./cmd/ec2sim)
