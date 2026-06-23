#!/bin/bash
set -euo pipefail
SCENARIO="${1:-/app/scenarios/release_candidate.json}"
OUT="${2:-/app/out/pipeline}"
go run ./cmd/pipelinesim run --scenario "$SCENARIO" --out "$OUT"
