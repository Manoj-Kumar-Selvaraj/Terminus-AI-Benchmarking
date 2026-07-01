#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/app}"
BUILD_DIR="${BUILD_DIR:-/app/build}"
BIN="${BUILD_DIR}/finbulk"
export PATH="/usr/bin:${PATH}"

BATCH=""
INPUT=""
DB=""
OUT=""
ABEND_AFTER="0"
ABEND_AFTER_LIM_MASTER="0"
CONTROL=""
CLOSE_DATE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --batch) BATCH="$2"; shift 2 ;;
        --input) INPUT="$2"; shift 2 ;;
        --db) DB="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        --abend-after) ABEND_AFTER="$2"; shift 2 ;;
        --abend-after-lim-master) ABEND_AFTER_LIM_MASTER="1"; shift 1 ;;
        --control) CONTROL="$2"; shift 2 ;;
        --close) CLOSE_DATE="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 99 ;;
    esac
done

if [[ -n "$CLOSE_DATE" ]]; then
    if [[ -z "$DB" || -z "$OUT" ]]; then
        echo "usage: run_finbulk.sh --close DATE --db PATH --out PATH" >&2
        exit 99
    fi
elif [[ -z "$INPUT" || -z "$DB" || -z "$OUT" ]]; then
    echo "usage: run_finbulk.sh --input PATH --db PATH --out PATH [--batch ID] [--abend-after N] [--abend-after-lim-master] [--control PATH]" >&2
    echo "       run_finbulk.sh --close DATE --db PATH --out PATH" >&2
    exit 99
fi

mkdir -p "$BUILD_DIR" "$OUT"
(cd "$APP_DIR" && go build -o "$BIN" ./cmd/finbulk)

if [[ -n "$CLOSE_DATE" ]]; then
    exec "$BIN" --close "$CLOSE_DATE" --db "$DB" --out "$OUT"
fi

ARGS=(--input "$INPUT" --db "$DB" --out "$OUT" --abend-after "$ABEND_AFTER")
[[ -n "$BATCH" ]] && ARGS+=(--batch "$BATCH")
[[ -n "$CONTROL" ]] && ARGS+=(--control "$CONTROL")
[[ "$ABEND_AFTER_LIM_MASTER" == "1" ]] && ARGS+=(--abend-after-lim-master)
exec "$BIN" "${ARGS[@]}"
