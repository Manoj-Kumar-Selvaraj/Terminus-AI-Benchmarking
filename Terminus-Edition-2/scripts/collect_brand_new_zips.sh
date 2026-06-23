#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/brand-new-task-zips"
mkdir -p "${OUT}/zips" "${OUT}/rubrics"

find_newest_zip() {
  local task="$1"
  local best="" best_mtime=0 mtime zip
  for dir in "${ROOT}/All-revision-new" "${ROOT}/new-task-upload" "${ROOT}/submission_zips"; do
    [[ -d "$dir" ]] || continue
    shopt -s nullglob
    for zip in "${dir}/${task}.zip" "${dir}/${task}"_*.zip; do
      [[ -f "$zip" ]] || continue
      mtime=$(stat -c %Y "$zip")
      if (( mtime > best_mtime )); then
        best_mtime=$mtime
        best=$zip
      fi
    done
    shopt -u nullglob
  done
  printf '%s' "$best"
}

copied=0
missing=()

for rubric in "${ROOT}/new-task-rubrics"/*.rubric.txt; do
  [[ -f "$rubric" ]] || continue
  task=$(basename "$rubric" .rubric.txt)
  zip=$(find_newest_zip "$task")
  if [[ -z "$zip" ]]; then
    missing+=("$task")
    continue
  fi
  cp "$zip" "${OUT}/zips/$(basename "$zip")"
  cp "$rubric" "${OUT}/rubrics/$(basename "$rubric")"
  echo "OK  $task <- $(basename "$zip")"
  copied=$((copied + 1))
done

# Pull in latest All-revision-new zips not yet copied (by basename)
if [[ -d "${ROOT}/All-revision-new" ]]; then
  shopt -s nullglob
  for zip in "${ROOT}/All-revision-new"/*.zip; do
    base=$(basename "$zip")
    [[ -f "${OUT}/zips/${base}" ]] && continue
    task="${base%_20*.zip}"
    cp "$zip" "${OUT}/zips/${base}"
    if [[ -f "${ROOT}/new-task-rubrics/${task}.rubric.txt" ]]; then
      cp "${ROOT}/new-task-rubrics/${task}.rubric.txt" "${OUT}/rubrics/${task}.rubric.txt"
    elif [[ -f "${ROOT}/${task}/rubric.txt" ]]; then
      cp "${ROOT}/${task}/rubric.txt" "${OUT}/rubrics/${task}.rubric.txt"
    fi
    echo "ADD $task <- ${base}"
    copied=$((copied + 1))
  done
  shopt -u nullglob
fi

{
  echo "# Brand-new task submission packages"
  echo ""
  echo "Generated: $(date -u +%Y-%m-%dT%H:%MZ)"
  echo ""
  echo "| Task | Zip | Rubric |"
  echo "|------|-----|--------|"
  shopt -s nullglob
  for zip in "${OUT}/zips"/*.zip; do
    base=$(basename "$zip")
    task="${base%_20*.zip}"
    [[ "$base" == "${task}.zip" ]] || task="${base%.zip}"
    rubric="${task}.rubric.txt"
    [[ -f "${OUT}/rubrics/${rubric}" ]] && rub="rubrics/${rubric}" || rub="(paste from task folder)"
    echo "| \`${task}\` | \`zips/${base}\` | \`${rub}\` |"
  done
  shopt -u nullglob
  if ((${#missing[@]} > 0)); then
    echo ""
    echo "## Missing zips (rebuild with zip.sh)"
    for t in "${missing[@]}"; do
      echo "- $t"
    done
  fi
} > "${OUT}/MANIFEST.md"

echo "---"
echo "Folder: ${OUT}"
echo "Zips:   $(find "${OUT}/zips" -name '*.zip' | wc -l)"
echo "Rubrics: $(find "${OUT}/rubrics" -name '*.rubric.txt' | wc -l)"
if ((${#missing[@]} > 0)); then
  echo "Missing: ${missing[*]}"
fi
