# Go Task Template (Terminus Edition 2)

Use this template for every `go-*` reconciliation / matcher task. The canonical reference is **`go-lab-sample-chain-reassignment`** (submission `b8294c8e-24d3-4599-af82-7faddc2de361`), which passes all portal quality checks and agent review with **READY TO USE**.

## Layout

```text
go-<domain>-<action>/
  task.toml
  rubric.txt                    # local authoring only — exclude from submission zip
  environment/                  # ONLY this tree is copied into the Docker image
    Dockerfile
    .dockerignore
    go.mod
    cmd/reconcile/main.go
    internal/reconcile/*.go       # broken starter the agent fixes
    data/*.csv                    # minimal shipped samples
    config/*.csv                  # aliases, reasons, windows, etc.
    docs/                         # record_layouts.md, operations.md
    samples/
    scripts/run_batch.sh
  steps/milestone_N/
    instruction.md
    tests/test.sh
    tests/test_mN.py
    solution/solve.sh             # chains solveN.sh in same directory
    solution/solveN.sh            # incremental oracle (self-contained heredocs)
```

## Mandatory `task.toml`

Include **top-level** timeouts **and** per-milestone blocks:

```toml
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous@example.com"
difficulty = "hard"
category = "software-engineering"
subcategories = ["tool_specific"]
number_of_milestones = 3
codebase_size = "small"
languages = ["go"]
tags = ["go", "csv", "reconciliation", "debugging", "incremental"]
expert_time_estimate_min = 150
junior_time_estimate_min = 360

[environment]
allow_internet = false
build_timeout_sec = 1200.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[agent]
timeout_sec = 1800.0

[verifier]
timeout_sec = 900.0

[[steps]]
name = "milestone_1"

[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0

# Repeat [[steps]] for milestone_2, milestone_3, ...
```

Rules:

- Keep **5–6 tags** max; avoid redundant tags like `data-processing` when category already conveys domain.
- Root `[agent]` / `[verifier]` sections are required alongside per-step blocks.
- Set `allow_internet = false` and ensure the Dockerfile does not require network at build time (see Dockerfile section).

## Dockerfile (preferred: `golang:` base)

**Preferred pattern** (offline-safe for AutoEval — matches `go-utility-refund-reconciler`):

```dockerfile
FROM golang:1.22.12-bookworm@sha256:3d699e4d15d0f8f13c9195c0632a16702b8cbdece2955af1c23b37ae5d55a253

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates=20230311+deb12u1 \
        python3=3.11.2-1+b1 \
        python3-pip=23.0.1+dfsg-1 \
        tmux=3.3a-3 \
        asciinema=2.2.0-1 \
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/go/bin:${PATH}"

COPY go.mod /app/go.mod
COPY cmd/ /app/cmd/
COPY internal/ /app/internal/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh
```

**Known deviation on reference task:** `go-lab-sample-chain-reassignment` still uses `debian:bookworm-slim` + `curl go.dev` to install Go. That works locally when Docker has internet but **fails AutoEval cloud builds** when `allow_internet = false`. Migrate to the `golang:` base above before expecting AutoEval build to pass.

Dockerfile rules:

- Digest-pinned base image
- Install `tmux`, `asciinema`, `python3`, `python3-pip` in the image
- Pin `pytest==8.4.1` and `pytest-json-ctrf==0.3.5` in Dockerfile (not in `test.sh`)
- Pin apt packages with explicit versions where possible
- Never `COPY` `steps/`, `tests/`, or `solution/`
- Always ship `environment/.dockerignore`

## `run_batch.sh`

```bash
#!/bin/bash
set -euo pipefail
cd /app
mkdir -p /app/build /app/out
GO_BIN="/usr/local/go/bin/go"
if [ ! -x "$GO_BIN" ]; then GO_BIN="go"; fi
"$GO_BIN" build -o /app/build/reconcile /app/cmd/reconcile/main.go
/app/build/reconcile
```

Adjust the binary name and `main.go` path to match your task.

## Canonical `tests/test.sh` (every milestone)

Use explicit exit-code capture (do not rely on `$?` after a separate `echo`):

```bash
#!/bin/bash
# Omit -e so pytest failures reach the reward if/else block below.
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_mN.py -rA
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Do **not** use `trap`, `set -e` before pytest, or runtime `pip`/`apt`/`curl` in `test.sh`.

## Test patterns (`test_mN.py`)

Follow the reference task's anti-cheat structure:

1. **Compile from source** — `build_program()` runs `go build` against `/app/cmd/reconcile/main.go` before each test.
2. **Runtime fixture injection** — `write_inputs()` overwrites `/app/data/*.csv` and `/app/config/*.csv` per test; shipped samples are never used as answers.
3. **Delete stale outputs** — unlink report/summary files before each run.
4. **Cross-check summary** — helper like `assert_summary_matches_rows()` validates summary arithmetic against report rows.
5. **Descriptive test names and docstrings** — each test function states exactly what behavior it verifies.

Minimal helper skeleton:

```python
APP = Path("/app")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "accessions.csv"
REPORT = APP / "out" / "reassignment_report.csv"

def build_program():
    subprocess.run(["go", "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP)

def write_inputs(source_rows, action_rows, ...):
    # overwrite CSVs, delete REPORT/SUMMARY
    ...

def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP)
    # parse report + summary
```

## Oracle / solution scripts

Harbor mounts only the **current milestone** `/solution/` directory. Each milestone's `solveN.sh` must be **self-contained** (full Go source rewrite via heredocs), or `solve.sh` must call scripts in the **same** directory:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve2.sh"
```

Do **not** rely on `../../milestone_1/solution/solve1.sh` paths in portal runs.

**Incremental oracle chain** (reference task pattern):

| Milestone | `solveN.sh` scope |
|-----------|-------------------|
| M1 | Exact identity gates, amount parsing, status/reason/kind gates, earliest-by-CSV-index tie-break, consumption |
| M2 | M1 rules + config-driven alias normalization (`kind_aliases.csv`) |
| M3 | M2 rules + window eligibility (`windows.csv`), reason config (`reasons.csv`), latest-source tie-break |

Each `solveN.sh` ends with `/app/scripts/run_batch.sh` to compile and run against runtime inputs.

## Instruction checklist (typical 3-milestone Go matcher)

| Milestone | Typical scope |
|-----------|----------------|
| M1 | Full-id match (all identity fields), amount parsing rules, status gate, reason literal set, kind normalization, timestamp ordering, one-time source consumption, earliest-by-**CSV row index** tie-break, report schema, `MATCHED`/`UNMATCHED`, blank fields on unmatched, summary key=value format |
| M2 | Config-driven aliases, case folding, canonical kind output, runtime-authoritative config CSVs |
| M3 | Window eligibility (`OPEN`/`CLOSED`), inclusive bounds, `action_ts <= close_ts`, data-driven reasons, latest-source tie-break with index fallback |

Document literal `MATCHED`/`UNMATCHED`, output file paths, and CSV column names in **M1**, not only in later milestones. State tie-break rules explicitly (e.g. "earliest by CSV row index, not by timestamp value") to avoid instruction-sufficiency failures.

## Platform pipeline (why AutoEval always runs)

Every `stb submissions update` triggers the full automated pipeline, **regardless of how trivial the revision fix is**:

```text
stb submissions update
  → zip upload
  → AutoEval (cloud Docker build + oracle)
  → Quality check (LLMaJ)
  → Agent review
  → Difficulty check (nop + oracle + frontier agent trials)
  → Human reviewer queue (when --send-to-reviewer, the default)
```

A small fix (e.g. trimming tags, fixing `test.sh` exit-code capture) does **not** skip AutoEval or agent difficulty runs. The portal re-runs the entire eval stack on every resubmit.

### Reading feedback layers separately

| Layer | What it means | Example on reference task |
|-------|---------------|---------------------------|
| **AutoEval build** | Cloud Docker image build | FAILED — `curl go.dev` blocked when `allow_internet = false` |
| **AutoEval oracle** | Cloud oracle run | Blocked when build fails |
| **Quality check** | LLMaJ static analysis | All pass |
| **Agent review** | Structural/metadata review | WARNING (tags), RECOMMENDATION: READY TO USE |
| **Difficulty check** | Real agent pass rates | MEDIUM (40–80% on frontier models) |

Do not conflate **BUILD FAILED** with **TRIVIAL difficulty**. A task can be structurally excellent (quality pass, READY TO USE) while AutoEval build still fails due to Dockerfile/network mismatch.

To skip sending to human reviewer while testing AutoEval only:

```bash
stb submissions update ./my-task -s SUBMISSION_ID --time MINUTES --no-send-to-reviewer
```

AutoEval still runs; only reviewer notification is suppressed.

## Pre-submit

```bash
bash scripts/terminus2_cli.sh preflight go-<task>
bash scripts/oracle_cumulative_go.sh go-<task>    # or terminus2_cli.sh oracle
bash scripts/zip.sh go-<task>
bash scripts/submit_task.sh go-<task> <submission-id> 90
```

- Pack with `scripts/zip.sh` (never ad-hoc `zip -r`); rubric excluded by default.
- Submit with `scripts/submit_task.sh` so the upload zip matches `zip_task.sh` validation.
- Verify the zip's `task.toml` contains `[agent]` and `[verifier]` before upload.
- Paste rubrics in the Snorkel UI; keep `rubric.txt` in the task folder for authoring but exclude it from the zip.

## Known open item on reference task

`go-lab-sample-chain-reassignment` is structurally sound but its Dockerfile still downloads Go via `curl go.dev`. When AutoEval build must pass, switch to the `golang:1.22.12-bookworm@sha256:…` base pattern shown above (same fix applied to `go-utility-refund-reconciler`).
