#!/bin/bash
# Replace noncanonical trap-based milestone test.sh with canonical reward-writing template.
# Normalize all .sh files under each task to LF line endings.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fixed_test_sh=0
skipped_test_sh=0
lf_normalized=0
tasks=0

write_canonical_test_sh() {
  local file="$1"
  local pytest_line="$2"
  cat >"$file" <<EOF
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

${pytest_line}

if [ \$? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
EOF
}

for task_dir in */; do
  [ -f "${task_dir}task.toml" ] || continue
  tasks=$((tasks + 1))
  task="${task_dir%/}"

  while IFS= read -r -d '' shfile; do
    sed -i 's/\r$//' "$shfile"
    lf_normalized=$((lf_normalized + 1))
  done < <(find "$task" -name '*.sh' -print0)

  while IFS= read -r test_sh; do
    [ -f "$test_sh" ] || continue

    if ! grep -qF "trap 'exit \$pytest_status' EXIT" "$test_sh" 2>/dev/null; then
      skipped_test_sh=$((skipped_test_sh + 1))
      continue
    fi

    pytest_line="$(grep -E '^[[:space:]]*(python3 -m pytest|pytest )' "$test_sh" | head -1 | sed 's/^[[:space:]]*//' || true)"
    if [ -z "$pytest_line" ]; then
      test_dir="$(dirname "$test_sh")"
      test_py="$(find "$test_dir" -maxdepth 1 -name 'test_*.py' | head -1)"
      if [ -n "$test_py" ]; then
        base="$(basename "$test_py")"
        pytest_line="python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/${base} -rA"
      else
        echo "WARN: no pytest line in $test_sh" >&2
        continue
      fi
    fi

    write_canonical_test_sh "$test_sh" "$pytest_line"
    fixed_test_sh=$((fixed_test_sh + 1))
  done < <(find "$task/steps" -path '*/tests/test.sh' 2>/dev/null | sort)
done

echo "Tasks processed: $tasks"
echo "test.sh rewritten (trap removed): $fixed_test_sh"
echo "test.sh already canonical: $skipped_test_sh"
echo "Shell files LF-normalized: $lf_normalized"

remaining="$(grep -rlF "trap 'exit \$pytest_status' EXIT" --include='test.sh' . 2>/dev/null | wc -l | tr -d ' ' || true)"
echo "Remaining trap test.sh files: ${remaining:-0}"
[ "${remaining:-0}" -eq 0 ]
