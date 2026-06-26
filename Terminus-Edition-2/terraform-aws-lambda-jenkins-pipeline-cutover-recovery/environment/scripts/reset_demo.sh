#!/usr/bin/env bash
set -Eeuo pipefail
rm -rf /app/state/*
/opt/task-tools/lambda-pipeline-runtime reset >/dev/null
/app/scripts/build.sh
/app/bin/pipelinectl deploy --infra /app/infra
