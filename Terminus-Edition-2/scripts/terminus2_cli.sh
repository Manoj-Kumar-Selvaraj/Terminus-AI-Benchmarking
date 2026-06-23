#!/usr/bin/env bash
set -euo pipefail

# Terminus Edition 2 local automation.
# Run from WSL/Linux:
#   ./scripts/terminus2_cli.sh preflight ./cobol-ach-reversal-reconciliation
#   ./scripts/terminus2_cli.sh oracle ./cobol-ach-reversal-reconciliation
#   ./scripts/terminus2_cli.sh check ./cobol-ach-reversal-reconciliation
#   ./scripts/terminus2_cli.sh full ./cobol-ach-reversal-reconciliation
#   ./scripts/terminus2_cli.sh zip ./cobol-ach-reversal-reconciliation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DEFAULT_STB_BIN="stb"
DEFAULT_HARBOR_BIN="harbor"
if [ -x "$HOME/.local/bin/stb" ]; then
  DEFAULT_STB_BIN="$HOME/.local/bin/stb"
fi
if [ -x "$HOME/.local/bin/harbor" ]; then
  DEFAULT_HARBOR_BIN="$HOME/.local/bin/harbor"
fi
if [ "$HOME" = "/root" ] && [ -x /root/.local/bin/stb ]; then
  DEFAULT_STB_BIN="/root/.local/bin/stb"
fi
if [ "$HOME" = "/root" ] && [ -x /root/.local/bin/harbor ]; then
  DEFAULT_HARBOR_BIN="/root/.local/bin/harbor"
fi

STB_BIN="${STB_BIN:-$DEFAULT_STB_BIN}"
HARBOR_BIN="${HARBOR_BIN:-$DEFAULT_HARBOR_BIN}"
MODEL_GPT="${MODEL_GPT:-@openai/gpt-5.2}"
MODEL_CLAUDE="${MODEL_CLAUDE:-@anthropic/claude-opus-4-6}"
AGENT_ONLY_MODEL="${AGENT_ONLY_MODEL:-}"
AGENT_TRIALS="${AGENT_TRIALS:-1}"
RUN_REAL_AGENTS="${RUN_REAL_AGENTS:-0}"
RUN_ZIP="${RUN_ZIP:-0}"
TIMEOUT_ORACLE_SEC="${TIMEOUT_ORACLE_SEC:-1800}"
TIMEOUT_CHECK_SEC="${TIMEOUT_CHECK_SEC:-1800}"
TIMEOUT_AGENT_SEC="${TIMEOUT_AGENT_SEC:-1800}"
HARBOR_STAGE_DELAY_SEC="${HARBOR_STAGE_DELAY_SEC:-20}"
HARBOR_ERRNO2_RETRY_DELAY_SEC="${HARBOR_ERRNO2_RETRY_DELAY_SEC:-60}"

usage() {
  cat <<'EOF'
Usage:
  terminus2_cli.sh <command> <task-path>

Commands:
  preflight   Run local structural checks only, no Docker/stb needed
  oracle      Run preflight + stb harbor oracle
  nop         Run preflight + NOP baseline
  check       Run preflight + stb harbor tasks check
  agents      Run real-agent trials with GPT-5.2 and Claude Opus 4.6
  full        Run preflight + oracle + CI/LLMaJ checks; real agents optional
  zip         Create a submission zip containing task files, not the parent folder

Environment knobs:
  RUN_REAL_AGENTS=1       Include real-agent trials in "full"
  AGENT_TRIALS=5          Number of runs per real agent (5 GPT + 5 Claude is the target)
  RUN_ZIP=1               Build zip at the end of "full"
  STB_BIN=stb             stb binary path
  USE_DIRECT_HARBOR=1     Skip stb and use Docker cumulative oracle when supported
  MODEL_GPT=@openai/gpt-5.2
  MODEL_CLAUDE=@anthropic/claude-opus-4-6
EOF
}

log() { printf '[%s] %s\n' "$(date +'%H:%M:%S')" "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

require_stb() {
  command -v "$STB_BIN" >/dev/null 2>&1 || die "stb CLI not found. Install with: uv tool install snorkelai-stb --find-links https://snorkel-python-wheels.s3.us-west-2.amazonaws.com/stb/index.html --python \">=3.12\""
}

stb_credentials_valid() {
  if [ "${USE_DIRECT_HARBOR:-0}" = "1" ]; then
    return 1
  fi
  local verify_out=""
  if ! command -v "$STB_BIN" >/dev/null 2>&1; then
    return 1
  fi
  if ! "$STB_BIN" keys show >/dev/null 2>&1; then
    return 1
  fi
  verify_out="$("$STB_BIN" keys verify 2>&1 || true)"
  if echo "$verify_out" | grep -qiE 'invalid|expired|Error:'; then
    return 1
  fi
  return 0
}

have_stb_credentials() {
  stb_credentials_valid
}

require_stb_credentials() {
  require_stb
  have_stb_credentials || die "No Snorkel AI credentials found. Export OPENAI_API_KEY and OPENAI_BASE_URL, or run: $STB_BIN login && $STB_BIN keys refresh"
}

has_direct_harbor() {
  command -v "$HARBOR_BIN" >/dev/null 2>&1
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker CLI not found in WSL/Linux."
  docker info >/dev/null 2>&1 || die "Docker is not reachable. Start Docker Desktop and make sure WSL integration is enabled."
}

have_timeout() {
  command -v timeout >/dev/null 2>&1
}

run_with_timeout() {
  local seconds="$1"
  shift
  if have_timeout; then
    timeout --kill-after=10 "$seconds" "$@"
  else
    "$@"
  fi
}

resolve_task() {
  local task_arg="$1"
  if [ -d "$task_arg" ]; then
    cd "$task_arg" && pwd
  elif [ -d "$ROOT_DIR/$task_arg" ]; then
    cd "$ROOT_DIR/$task_arg" && pwd
  else
    die "Task directory not found: $task_arg"
  fi
}

new_log_dir() {
  local task_dir="$1"
  local dir="$ROOT_DIR/.terminus_logs/$(basename "$task_dir")"
  mkdir -p "$dir"
  echo "$dir"
}

run_preflight() {
  local task_dir="$1"
  log "Running local preflight for $(basename "$task_dir")"
  python3 - "$task_dir" <<'PY'
import os
import re
import sys
from pathlib import Path

task = Path(sys.argv[1])
errors: list[str] = []
warnings: list[str] = []

def err(msg: str) -> None:
    errors.append(msg)

def warn(msg: str) -> None:
    warnings.append(msg)

def require(path: str) -> None:
    if not (task / path).exists():
        err(f"missing required path: {path}")

toml_path = task / "task.toml"
if not toml_path.exists():
    err("missing required path: task.toml")
    data = {}
else:
    raw_toml = toml_path.read_text(encoding="utf-8")
    try:
        import tomllib
        data = tomllib.loads(raw_toml)
    except ModuleNotFoundError:
        try:
            import tomli
            data = tomli.loads(raw_toml)
        except ModuleNotFoundError:
            data = {}
            current = data
            current_array_item = None

            def parse_value(value: str):
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    return value[1:-1]
                if value.startswith("[") and value.endswith("]"):
                    body = value[1:-1].strip()
                    if not body:
                        return []
                    return [parse_value(part.strip()) for part in body.split(",") if part.strip()]
                if value.lower() in {"true", "false"}:
                    return value.lower() == "true"
                try:
                    if "." in value:
                        return float(value)
                    return int(value)
                except ValueError:
                    return value

            for line in raw_toml.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                if line == "[[steps]]":
                    data.setdefault("steps", []).append({})
                    current = data["steps"][-1]
                    current_array_item = current
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                    if section.startswith("steps.") and current_array_item is not None:
                        _, sub = section.split(".", 1)
                        current_array_item.setdefault(sub, {})
                        current = current_array_item[sub]
                    else:
                        current = data
                        for part in section.split("."):
                            current = current.setdefault(part, {})
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    current[key.strip()] = parse_value(value)

metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
milestones = int(metadata.get("number_of_milestones", -1))

required_meta = [
    "author_name",
    "author_email",
    "difficulty",
    "category",
    "subcategories",
    "number_of_milestones",
    "codebase_size",
    "languages",
    "tags",
    "expert_time_estimate_min",
    "junior_time_estimate_min",
]
if data.get("version") != "2.0":
    err('task.toml version must be "2.0"')
for key in required_meta:
    if key not in metadata:
        err(f"task.toml missing [metadata].{key}")

env = data.get("environment", {}) if isinstance(data, dict) else {}
for key in ["build_timeout_sec", "cpus", "memory_mb", "storage_mb"]:
    if key not in env:
        err(f"task.toml missing [environment].{key}")

require("environment")
if not (task / "environment" / "Dockerfile").exists() and not (task / "environment" / "docker-compose.yaml").exists():
    err("environment must contain Dockerfile or docker-compose.yaml")

if milestones <= 0:
    require("instruction.md")
    require("solution/solve.sh")
    require("tests/test.sh")
    require("tests/test_outputs.py")
    if "agent" not in data or "timeout_sec" not in data.get("agent", {}):
        err("non-milestone task.toml missing [agent].timeout_sec")
    if "verifier" not in data or "timeout_sec" not in data.get("verifier", {}):
        err("non-milestone task.toml missing [verifier].timeout_sec")
else:
    if milestones < 2:
        err("milestone tasks must have at least 2 milestones")
    for forbidden in ["instruction.md", "solution", "tests"]:
        if (task / forbidden).exists():
            err(f"milestone task must not include root-level {forbidden}")
    steps = data.get("steps", [])
    if len(steps) != milestones:
        err("number_of_milestones must equal the number of [[steps]] blocks")
    for i in range(1, milestones + 1):
        base = f"steps/milestone_{i}"
        require(f"{base}/instruction.md")
        require(f"{base}/tests/test.sh")
        py_test = f"{base}/tests/test_m{i}.py"
        rb_test = f"{base}/tests/test_m{i}.rb"
        if not (task / py_test).exists() and not (task / rb_test).exists():
            err(f"missing required path: {py_test} (or {rb_test})")
        require(f"{base}/solution/solve.sh")
        solve_sh = task / f"{base}/solution/solve.sh"
        solve_text = solve_sh.read_text(encoding="utf-8") if solve_sh.exists() else ""
        if re.search(rf'\\$SCRIPT_DIR/solve{i}\\.sh|bash\\s+.*solve{i}\\.sh', solve_text):
            require(f"{base}/solution/solve{i}.sh")

instruction_paths = []
if milestones <= 0:
    instruction_paths.append(task / "instruction.md")
else:
    instruction_paths.extend(task / "steps" / f"milestone_{i}" / "instruction.md" for i in range(1, milestones + 1))

for path in instruction_paths:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    if "canary" in text.lower():
        err(f"{path.relative_to(task)} contains a canary string")
    refs = []
    for token in re.split(r"\s+", text):
        token = token.strip("`'\".,:;()[]{}")
        if "/" not in token or token.startswith("/") or "://" in token:
            continue
        refs.append(token)
    relative_refs = refs
    if relative_refs:
        warn(f"{path.relative_to(task)} may contain relative paths: {', '.join(sorted(set(relative_refs))[:5])}")

docker_text = ""
for docker_path in [task / "environment" / "Dockerfile", task / "environment" / "docker-compose.yaml"]:
    if docker_path.exists():
        docker_text += "\n" + docker_path.read_text(encoding="utf-8", errors="ignore")
if re.search(r"\bCOPY\s+(tests|solution|steps)/", docker_text):
    err("Docker environment appears to copy tests, solution, or steps into the image")
if re.search(r"\b(privileged:\s*true|--privileged)\b", docker_text):
    err("Docker environment uses privileged mode")
if re.search(r"\b(FROM|image:)\s+[^@\s:]+:latest\b", docker_text):
    err("Docker base/service image uses latest tag")

for file_path in task.rglob("*"):
    if not file_path.is_file():
        continue
    rel = file_path.relative_to(task)
    if "terminus_logs" in rel.parts:
        continue
    if file_path.stat().st_size > 1_000_000:
        err(f"file exceeds 1MB: {rel}")

env_files = [p for p in (task / "environment").rglob("*") if p.is_file()] if (task / "environment").exists() else []
codebase_size = metadata.get("codebase_size")
if codebase_size == "minimal" and len(env_files) >= 20:
    warn(f"codebase_size is minimal but environment has {len(env_files)} files")
if codebase_size == "small" and len(env_files) < 20:
    err(f"codebase_size is small but environment has only {len(env_files)} files")
if codebase_size == "large" and len(env_files) < 200:
    warn(f"codebase_size is large but environment has only {len(env_files)} files")

print(f"Environment file count: {len(env_files)}")
for warning in warnings:
    print(f"WARNING: {warning}")
if errors:
    for error in errors:
        print(f"ERROR: {error}")
    raise SystemExit(1)
print("Preflight passed.")
PY
}

task_supports_docker_cumulative_oracle() {
  local task_dir="$1"
  [ -f "$task_dir/task.toml" ] || return 1
  grep -qiE 'languages\s*=\s*\[.*"(go|bash|ruby|cobol|pl1)".*\]' "$task_dir/task.toml"
}

run_docker_cumulative_oracle() {
  local task_dir="$1"
  local log_file="$2"
  local task_name milestones m
  task_name="$(basename "$task_dir")"
  milestones="$(python3 - "$task_dir/task.toml" <<'PY'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"number_of_milestones\s*=\s*(\d+)", text)
print(match.group(1) if match else "0")
PY
)"
  if [ "$milestones" -le 0 ]; then
    return 1
  fi
  log "Using Docker cumulative oracle for ${task_name} (stb credentials unavailable or invalid)."
  set +e
  if grep -qiE '"(go|bash|ruby|cobol|pl1)"' "$task_dir/task.toml"; then
    run_with_timeout "$TIMEOUT_ORACLE_SEC" bash "$ROOT_DIR/scripts/oracle_cumulative_go.sh" "$task_name" 2>&1 | tee "$log_file"
  else
    set -e
    return 1
  fi
  local rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

run_oracle() {
  local task_dir="$1"
  local log_dir="$2"
  require_docker
  local log_file="$log_dir/oracle_$(date +'%Y%m%d_%H%M%S').log"
  local jobs_dir="$log_dir/jobs_oracle_$(date +'%Y%m%d_%H%M%S')_$RANDOM"
  log "Running oracle. Log: $log_file"
  local rc=0
  if command -v "$STB_BIN" >/dev/null 2>&1 && have_stb_credentials; then
    set +e
    run_with_timeout "$TIMEOUT_ORACLE_SEC" "$STB_BIN" harbor run -a oracle -p "$task_dir" --jobs-dir "$jobs_dir" 2>&1 | tee "$log_file"
    rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" -ne 0 ] && grep -qiE 'credentials are invalid|expired' "$log_file" 2>/dev/null && task_supports_docker_cumulative_oracle "$task_dir"; then
      run_docker_cumulative_oracle "$task_dir" "$log_file"
      return $?
    fi
  elif task_supports_docker_cumulative_oracle "$task_dir"; then
    run_docker_cumulative_oracle "$task_dir" "$log_file"
    return $?
  elif has_direct_harbor; then
    log "No valid stb credentials found; using direct Harbor for oracle."
    set +e
    run_with_timeout "$TIMEOUT_ORACLE_SEC" "$HARBOR_BIN" run -a oracle -p "$task_dir" -o "$jobs_dir" 2>&1 | tee "$log_file"
    rc=${PIPESTATUS[0]}
    set -e
  else
    require_stb_credentials
  fi
  if [ "$rc" -ne 0 ] && grep -q "Errno 2" "$log_file" 2>/dev/null; then
    log "Oracle hit Harbor Errno 2 before job creation; waiting ${HARBOR_ERRNO2_RETRY_DELAY_SEC}s and retrying once."
    sleep "$HARBOR_ERRNO2_RETRY_DELAY_SEC"
    log_file="$log_dir/oracle_retry_$(date +'%Y%m%d_%H%M%S').log"
    jobs_dir="$log_dir/jobs_oracle_retry_$(date +'%Y%m%d_%H%M%S')_$RANDOM"
    log "Retrying oracle. Log: $log_file"
    if command -v "$STB_BIN" >/dev/null 2>&1 && have_stb_credentials; then
      run_with_timeout "$TIMEOUT_ORACLE_SEC" "$STB_BIN" harbor run -a oracle -p "$task_dir" --jobs-dir "$jobs_dir" 2>&1 | tee "$log_file"
    elif task_supports_docker_cumulative_oracle "$task_dir"; then
      run_docker_cumulative_oracle "$task_dir" "$log_file"
    else
      run_with_timeout "$TIMEOUT_ORACLE_SEC" "$HARBOR_BIN" run -a oracle -p "$task_dir" -o "$jobs_dir" 2>&1 | tee "$log_file"
    fi
  elif [ "$rc" -ne 0 ]; then
    if task_supports_docker_cumulative_oracle "$task_dir"; then
      run_docker_cumulative_oracle "$task_dir" "$log_file"
      return $?
    fi
    return "$rc"
  fi
}

run_nop() {
  local task_dir="$1"
  local log_dir="$2"
  require_docker
  local log_file="$log_dir/nop_$(date +'%Y%m%d_%H%M%S').log"
  local jobs_dir="$log_dir/jobs_nop_$(date +'%Y%m%d_%H%M%S')_$RANDOM"
  log "Running NOP baseline. Log: $log_file"
  if command -v "$STB_BIN" >/dev/null 2>&1 && have_stb_credentials; then
    run_with_timeout "$TIMEOUT_ORACLE_SEC" "$STB_BIN" harbor run -a nop -p "$task_dir" --jobs-dir "$jobs_dir" 2>&1 | tee "$log_file"
  elif has_direct_harbor; then
    log "No stb credentials found; using direct Harbor for NOP."
    run_with_timeout "$TIMEOUT_ORACLE_SEC" "$HARBOR_BIN" run -a nop -p "$task_dir" --jobs-dir "$jobs_dir" 2>&1 | tee "$log_file"
  else
    require_stb_credentials
  fi
}

run_check() {
  local task_dir="$1"
  local log_dir="$2"
  require_stb_credentials
  require_docker
  local stamp
  stamp="$(date +'%Y%m%d_%H%M%S')"
  local log_file="$log_dir/check_${stamp}.log"
  log "Running CI/LLMaJ checks. Log: $log_file"
  set +e
  run_with_timeout "$TIMEOUT_CHECK_SEC" "$STB_BIN" harbor check "$task_dir" 2>&1 | tee "$log_file"
  local rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

latest_result_json() {
  local jobs_dir="$1"
  find "$jobs_dir" -name result.json -type f 2>/dev/null | sort | tail -n 1
}

latest_trial_log() {
  local jobs_dir="$1"
  find "$jobs_dir" -name trial.log -type f 2>/dev/null | sort | tail -n 1
}

extract_reward_from_result() {
  local result_json="$1"
  if [ -z "$result_json" ] || [ ! -f "$result_json" ]; then
    echo "0.0"
    return
  fi
  python3 - "$result_json" <<'PY' 2>/dev/null || echo "0.0"
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

def numeric(value):
    try:
        return float(value)
    except Exception:
        return None

rewards = []

stats = data.get("stats") or {}
evals = stats.get("evals") or {}
if isinstance(evals, dict):
    iterable = evals.values()
elif isinstance(evals, list):
    iterable = evals
else:
    iterable = []

for item in iterable:
    if not isinstance(item, dict):
        continue
    for metric in item.get("metrics") or []:
        if isinstance(metric, dict):
            val = numeric(metric.get("mean"))
            if val is not None:
                rewards.append(val)
    reward_stats = item.get("reward_stats") or {}
    reward_bucket = reward_stats.get("reward") or {}
    if isinstance(reward_bucket, dict):
        for key, ids in reward_bucket.items():
            val = numeric(key)
            if val is None:
                continue
            if isinstance(ids, list):
                rewards.extend([val] * len(ids))
            else:
                rewards.append(val)

for trial in data.get("trials") or []:
    if isinstance(trial, dict):
        val = numeric(trial.get("reward"))
        if val is not None:
            rewards.append(val)

if rewards:
    print(max(rewards))
else:
    print("0.0")
PY
}

reward_is_pass() {
  awk -v r="$1" 'BEGIN { exit !(r + 0 >= 1.0) }'
}

append_failure_excerpt() {
  local report="$1"
  local title="$2"
  local file="$3"
  local lines="${4:-80}"
  echo "#### $title" >> "$report"
  if [ -f "$file" ]; then
    echo '```text' >> "$report"
    tail -n "$lines" "$file" >> "$report"
    echo '```' >> "$report"
  else
    echo "_Missing file: $file_" >> "$report"
  fi
  echo >> "$report"
}

run_agents() {
  local task_dir="$1"
  local log_dir="$2"
  require_stb_credentials
  require_docker
  local report="$log_dir/agent_runs_$(date +'%Y%m%d_%H%M%S').md"
  log "Running real-agent trials. Report: $report"
  {
    echo "# Real Agent Trials"
    echo
    echo "Task: $(basename "$task_dir")"
    echo "Trials per model: $AGENT_TRIALS"
    echo "GPT model: $MODEL_GPT"
    echo "Claude model: $MODEL_CLAUDE"
    echo
  } > "$report"
  local models=("$MODEL_GPT" "$MODEL_CLAUDE")
  if [ -n "$AGENT_ONLY_MODEL" ]; then
    models=("$AGENT_ONLY_MODEL")
  fi
  for model in "${models[@]}"; do
    echo "## $model" >> "$report"
    local pass_count=0
    local fail_count=0
    for i in $(seq 1 "$AGENT_TRIALS"); do
      local log_file="$log_dir/agent_${model//[\/@]/_}_${i}_$(date +'%Y%m%d_%H%M%S').log"
      local jobs_dir="$log_dir/jobs_agent_${model//[\/@]/_}_${i}_$(date +'%Y%m%d_%H%M%S')_$RANDOM"
      log "Agent run $i/$AGENT_TRIALS: $model"
      set +e
      run_with_timeout "$TIMEOUT_AGENT_SEC" "$STB_BIN" harbor run -m "$model" -p "$task_dir" --jobs-dir "$jobs_dir" 2>&1 | tee "$log_file"
      local rc=${PIPESTATUS[0]}
      set -e
      local result_json
      result_json="$(latest_result_json "$jobs_dir")"
      local trial_log
      trial_log="$(latest_trial_log "$jobs_dir")"
      local reward
      reward="$(extract_reward_from_result "$result_json")"
      if reward_is_pass "$reward"; then
        pass_count=$((pass_count + 1))
        echo "- Run $i: PASS reward=$reward rc=$rc" >> "$report"
      else
        fail_count=$((fail_count + 1))
        echo "- Run $i: FAIL reward=$reward rc=$rc" >> "$report"
      fi
      echo "  - log: $log_file" >> "$report"
      echo "  - jobs: $jobs_dir" >> "$report"
      if [ -n "$result_json" ]; then
        echo "  - result: $result_json" >> "$report"
      fi
      if [ -n "$trial_log" ]; then
        echo "  - trial: $trial_log" >> "$report"
      fi
      if ! reward_is_pass "$reward"; then
        append_failure_excerpt "$report" "Failure excerpt for $model run $i main log" "$log_file" 80
        if [ -n "$trial_log" ]; then
          append_failure_excerpt "$report" "Failure excerpt for $model run $i trial log" "$trial_log" 80
        fi
      fi
    done
    local rate
    rate="$(awk -v p="$pass_count" -v t="$AGENT_TRIALS" 'BEGIN { printf "%.0f", (p * 100.0 / t) }')"
    echo "- Pass rate: ${rate}% (${pass_count}/${AGENT_TRIALS})" >> "$report"
    echo "- Failures: ${fail_count}/${AGENT_TRIALS}" >> "$report"
    if [ "$rate" -ge 80 ]; then
      echo "- Difficulty warning: this model is at or above the 80% rejection threshold." >> "$report"
    elif [ "$rate" -le 20 ]; then
      echo "- Difficulty signal: this model is in hard-task range." >> "$report"
    else
      echo "- Difficulty signal: this model is in medium-task range." >> "$report"
    fi
    echo >> "$report"
  done
  log "Agent report ready: $report"
  log "Agent report contents:"
  sed 's/^/  /' "$report"
}

zip_task() {
  local task_dir="$1"
  local zip_dir="$ROOT_DIR/submission_zips"
  mkdir -p "$zip_dir"
  log "Creating submission zip via scripts/zip.sh"
  bash "$ROOT_DIR/scripts/zip.sh" --task "$task_dir" --out "$zip_dir"
}

main() {
  local command="${1:-}"
  local task_arg="${2:-}"
  if [ -z "$command" ] || [ -z "$task_arg" ]; then
    usage
    exit 1
  fi

  local task_dir
  task_dir="$(resolve_task "$task_arg")"
  local log_dir
  log_dir="$(new_log_dir "$task_dir")"

  case "$command" in
    preflight)
      run_preflight "$task_dir"
      ;;
    oracle)
      run_preflight "$task_dir"
      run_oracle "$task_dir" "$log_dir"
      ;;
    nop)
      run_preflight "$task_dir"
      run_nop "$task_dir" "$log_dir"
      ;;
    check)
      run_preflight "$task_dir"
      run_check "$task_dir" "$log_dir"
      ;;
    agents)
      run_agents "$task_dir" "$log_dir"
      ;;
    full)
      run_preflight "$task_dir"
      # Run Harbor-backed stages in fresh shell processes. The stb/Harbor CLI can
      # occasionally leave process-local state after one run that makes the next
      # run fail before a job directory is created.
      bash "$0" nop "$task_dir"
      log "Waiting ${HARBOR_STAGE_DELAY_SEC}s for Harbor/Docker cleanup before oracle."
      sleep "$HARBOR_STAGE_DELAY_SEC"
      bash "$0" oracle "$task_dir"
      log "Waiting ${HARBOR_STAGE_DELAY_SEC}s for Harbor/Docker cleanup before checks."
      sleep "$HARBOR_STAGE_DELAY_SEC"
      bash "$0" check "$task_dir"
      if [ "$RUN_REAL_AGENTS" = "1" ]; then
        bash "$0" agents "$task_dir"
      else
        log "Skipping real agents. Set RUN_REAL_AGENTS=1 to include them."
      fi
      if [ "$RUN_ZIP" = "1" ]; then
        zip_task "$task_dir"
      fi
      ;;
    zip)
      run_preflight "$task_dir"
      zip_task "$task_dir"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
