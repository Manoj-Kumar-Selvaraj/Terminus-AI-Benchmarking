#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/app}"
BUILD_DIR="${BUILD_DIR:-/app/build}"
BIN="${BUILD_DIR}/finbulk"
export PATH="/usr/local/go/bin:${PATH}"

BATCH=""
INPUT=""
DB=""
OUT=""
ABEND_AFTER="0"
CONTROL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --batch) BATCH="$2"; shift 2 ;;
        --input) INPUT="$2"; shift 2 ;;
        --db) DB="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        --abend-after) ABEND_AFTER="$2"; shift 2 ;;
        --control) CONTROL="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 99 ;;
    esac
done

if [[ -z "$INPUT" || -z "$DB" || -z "$OUT" ]]; then
    echo "usage: run_finbulk.sh --input PATH --db PATH --out PATH [--batch ID] [--abend-after N] [--control PATH]" >&2
    exit 99
fi

mkdir -p "$BUILD_DIR" "$OUT"
if [[ ! -x "$BIN" ]]; then
    (cd "$APP_DIR" && go build -o "$BIN" ./cmd/finbulk)
fi

ARGS=(--input "$INPUT" --db "$DB" --out "$OUT" --abend-after "$ABEND_AFTER")
[[ -n "$BATCH" ]] && ARGS+=(--batch "$BATCH")
[[ -n "$CONTROL" ]] && ARGS+=(--control "$CONTROL")
exec "$BIN" "${ARGS[@]}"
