#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="${1:-}"
ZIP_DIR="${2:-$ROOT/Revision-ChatGpt/Task-Zip}"
BACKUP_DIR="${3:-$ROOT/Revision-ChatGpt/Backups}"

usage() {
  echo "Usage: $0 <task-name> [zip-dir] [backup-dir]" >&2
  echo "Example: $0 go-food-truck-rally-voucher-matcher" >&2
}

if [[ -z "$TASK" ]]; then
  usage
  exit 1
fi

TARGET="$ROOT/$TASK"

if [[ ! -d "$ZIP_DIR" ]]; then
  echo "Zip folder not found: $ZIP_DIR" >&2
  exit 1
fi

if [[ ! -d "$TARGET" ]]; then
  echo "Existing task folder not found: $TARGET" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

ZIP="$(
  find "$ZIP_DIR" -maxdepth 1 -type f -name "${TASK}*.zip" -printf '%T@ %p\n' \
    | sort -nr \
    | head -n 1 \
    | cut -d' ' -f2-
)"

if [[ -z "${ZIP:-}" ]]; then
  echo "No zip found for task '$TASK' in: $ZIP_DIR" >&2
  exit 1
fi

TMP="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "Using zip: $ZIP"
unzip -q "$ZIP" -d "$TMP"

EXTRACTED="$TMP/$TASK"
if [[ ! -d "$EXTRACTED" ]]; then
  EXTRACTED="$(find "$TMP" -mindepth 1 -maxdepth 3 -type d -name "$TASK" | head -n 1)"
fi

if [[ -z "${EXTRACTED:-}" && -f "$TMP/task.toml" && -d "$TMP/environment" && -d "$TMP/steps" ]]; then
  EXTRACTED="$TMP"
fi

if [[ -z "${EXTRACTED:-}" || ! -d "$EXTRACTED" ]]; then
  echo "Could not find extracted task folder named: $TASK" >&2
  echo "Zip contents start:" >&2
  find "$TMP" -maxdepth 3 -print >&2
  exit 1
fi

BACKUP="$BACKUP_DIR/${TASK}_backup_$(date +%Y%m%d_%H%M%S)"

echo "Backing up current task to: $BACKUP"
mv "$TARGET" "$BACKUP"

echo "Installing extracted task to: $TARGET"
if [[ "$EXTRACTED" == "$TMP" ]]; then
  mkdir -p "$TARGET"
  shopt -s dotglob
  mv "$TMP"/* "$TARGET"/
  shopt -u dotglob
else
  mv "$EXTRACTED" "$TARGET"
fi

echo "Done."
echo "Zip: $ZIP"
echo "Backup: $BACKUP"
echo "Installed: $TARGET"
