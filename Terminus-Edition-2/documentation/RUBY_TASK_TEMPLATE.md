# Ruby Task Template (Terminus Edition 2)

Use this template for every `ruby-*` reconciliation task. It matches the working reference tasks (`ruby-charity-pledge-adjustment-matcher`, `ruby-brewery-keg-deposit-reconciler`, `ruby-theater-booking-refund-matcher`) and avoids portal **7200s completion-marker** timeouts.

## Layout (two supported code roots)

Most tasks use **`environment/lib/reconcile.rb`**. Some use **`environment/app/reconcile.rb`**. Do not mix both in one task.

```text
ruby-<domain>-<action>/
  task.toml
  rubric.txt
  environment/
    Dockerfile
    .dockerignore
    lib/reconcile.rb          # OR app/reconcile.rb
    data/*.csv
    config/*.csv
    config/cutoff_calendar.txt
    docs/
    samples/
    scripts/run_batch.sh
  steps/milestone_N/
    instruction.md
    tests/test.sh
    tests/test_mN.py
    solution/solve.sh
    solution/solveN.sh
```

## Mandatory `task.toml`

Include **top-level** timeouts **and** per-milestone blocks:

```toml
[agent]
timeout_sec = 1800

[verifier]
timeout_sec = 900

[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[[steps]]
name = "milestone_1"

[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
```

Repeat `[[steps]]` for each milestone. Bulk fix: `python3 scripts/audit_fix_task_toml_timeouts.py`.

## Dockerfile (`lib/` layout)

```dockerfile
FROM ruby:3.3.5-slim@sha256:25a9df53c6f23406f6bc87426ad5bd74b6d99423a8c2ca630f2443dee2447f53

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates python3 python3-pip tmux \
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \
    && rm -rf /var/lib/apt/lists/*

COPY lib/ /app/lib/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh \
    && find /app/lib -name '*.rb' -exec chmod +x {} +
```

For **`app/`** layout, replace `COPY lib/` with `COPY app/ /app/app/` and `find /app/lib` with `find /app/app`.

Rules:

- Digest-pinned base image
- Install `bash`, `tmux`, `python3`, `python3-pip` in the image
- Pin `pytest==8.4.1` and `pytest-json-ctrf==0.3.5` in Dockerfile (not in `test.sh`)
- Never `COPY` `steps/`, `tests/`, or `solution/`
- Always ship `environment/.dockerignore`

## `run_batch.sh`

`lib/` tasks:

```bash
#!/usr/bin/env bash
set -euo pipefail
ruby /app/lib/reconcile.rb
```

`app/` tasks:

```bash
#!/usr/bin/env bash
set -euo pipefail
ruby /app/app/reconcile.rb
```

## Canonical `tests/test.sh` (every milestone)

```bash
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_mN.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
```

Do **not** use `trap`, `set -e` before pytest, or runtime `pip`/`apt`/`curl` in `test.sh`.

## Oracle / solution scripts

Harbor mounts only the **current milestone** `/solution/` directory. Each milestone’s `solveN.sh` must be **self-contained** (full `reconcile.rb` rewrite), or `solve.sh` must call scripts in the **same** directory:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve4.sh"
```

Do **not** rely on `../../milestone_1/solution/solve1.sh` paths in portal runs.

## Instruction checklist (typical 4-milestone Ruby matcher)

| Milestone | Typical scope |
|-----------|----------------|
| M1 | Full-id match, status gate, dimension equality, report schema, `MATCHED`/`UNMATCHED`, blank dimension on unmatched, positive summary JSON |
| M2 | Legacy aliases → canonical values, row consumption |
| M3 | `cutoff_calendar.txt`, open dates, latest source date, earliest-input tie-break |
| M4 | `methods.csv` eligibility gate (`enabled=true`, case/whitespace tolerant) |

Document literal `MATCHED`/`UNMATCHED` and empty CSV fields in **M1**, not only in later milestones.

## Normalize all Ruby tasks

```bash
python3 scripts/normalize_ruby_tasks.py
```

This updates Dockerfiles, `.dockerignore`, `run_batch.sh`, `task.toml` timeouts, canonical `test.sh` files, and LF line endings on `.sh` files.

## Pre-submit

```bash
bash scripts/terminus2_cli.sh preflight ruby-<task>
bash scripts/terminus2_cli.sh oracle ruby-<task>
bash scripts/zip_task.sh --task ruby-<task>
```

Verify the zip’s `task.toml` contains `[agent]` and `[verifier]` before upload.
