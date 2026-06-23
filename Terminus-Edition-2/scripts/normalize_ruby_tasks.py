#!/usr/bin/env python3
"""Normalize all ruby-* tasks to the Edition 2 Ruby submission template."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUBY_DIGEST = (
    "ruby:3.3.5-slim@sha256:25a9df53c6f23406f6bc87426ad5bd74b6d99423a8c2ca630f2443dee2447f53"
)

DOCKERIGNORE = """.git
.gitignore
**/__pycache__/
**/*.pyc
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/node_modules/
"""

DOCKERFILE_LIB = f"""FROM {RUBY_DIGEST}

WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends bash ca-certificates python3 python3-pip tmux \\
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \\
    && rm -rf /var/lib/apt/lists/*

COPY lib/ /app/lib/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \\
    && chmod +x /app/scripts/*.sh \\
    && find /app/lib -name '*.rb' -exec chmod +x {{}} +
"""

DOCKERFILE_APP = f"""FROM {RUBY_DIGEST}

WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends bash ca-certificates python3 python3-pip tmux \\
    && pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5 \\
    && rm -rf /var/lib/apt/lists/*

COPY app/ /app/app/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \\
    && chmod +x /app/scripts/*.sh \\
    && find /app/app -name '*.rb' -exec chmod +x {{}} +
"""

RUN_BATCH_LIB = """#!/usr/bin/env bash
set -euo pipefail
ruby /app/lib/reconcile.rb
"""

RUN_BATCH_APP = """#!/usr/bin/env bash
set -euo pipefail
ruby /app/app/reconcile.rb
"""

TEST_SH = """#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/{test_file} -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""

AGENT_TIMEOUT = 1800.0
VERIFIER_TIMEOUT = 900.0
BUILD_TIMEOUT = 900.0


def ruby_code_root(env: Path) -> str:
    if (env / "lib" / "reconcile.rb").is_file():
        return "lib"
    if (env / "app" / "reconcile.rb").is_file():
        return "app"
    raise SystemExit(f"{env.parent.name}: missing lib/reconcile.rb or app/reconcile.rb")


def parse_milestones(task_toml: str) -> int:
    names = re.findall(r'name\s*=\s*"milestone_\d+"', task_toml)
    if names:
        return len(names)
    m = re.search(r"number_of_milestones\s*=\s*(\d+)", task_toml)
    return int(m.group(1)) if m else 1


def build_task_toml(existing: str, milestones: int) -> str:
    version_match = re.search(r'^version\s*=\s*"[^"]+"', existing, re.M)
    version_line = version_match.group(0) if version_match else 'version = "2.0"'
    meta = re.search(r"(\[metadata\][\s\S]*?)(?=\n\[agent\]|\n\[environment\]|\n\[\[steps\]\]|\Z)", existing)
    if not meta:
        raise SystemExit("task.toml missing [metadata]")
    metadata_block = meta.group(1).rstrip() + "\n"
    metadata_block = re.sub(
        r"number_of_milestones\s*=\s*\d+",
        f"number_of_milestones = {milestones}",
        metadata_block,
        count=1,
    )
    steps = ""
    for i in range(1, milestones + 1):
        steps += f"""
[[steps]]
name = "milestone_{i}"

[steps.agent]
timeout_sec = {AGENT_TIMEOUT}
[steps.verifier]
timeout_sec = {VERIFIER_TIMEOUT}
"""
    return (
        f"{version_line}\n\n"
        + metadata_block
        + f"""
[agent]
timeout_sec = {int(AGENT_TIMEOUT)}

[verifier]
timeout_sec = {int(VERIFIER_TIMEOUT)}

[environment]
allow_internet = false
build_timeout_sec = {BUILD_TIMEOUT}
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"
"""
        + steps
    )


def normalize_task(task_dir: Path) -> list[str]:
    changes: list[str] = []
    env = task_dir / "environment"
    code_root = ruby_code_root(env)

    dockerfile = DOCKERFILE_LIB if code_root == "lib" else DOCKERFILE_APP
    df_path = env / "Dockerfile"
    if df_path.read_text(encoding="utf-8").replace("\r\n", "\n") != dockerfile:
        df_path.write_text(dockerfile, encoding="utf-8", newline="\n")
        changes.append("Dockerfile")

    di_path = env / ".dockerignore"
    if di_path.read_text(encoding="utf-8").replace("\r\n", "\n") != DOCKERIGNORE:
        di_path.write_text(DOCKERIGNORE, encoding="utf-8", newline="\n")
        changes.append(".dockerignore")

    rb_path = env / "scripts" / "run_batch.sh"
    run_batch = RUN_BATCH_LIB if code_root == "lib" else RUN_BATCH_APP
    if rb_path.read_text(encoding="utf-8").replace("\r\n", "\n") != run_batch:
        rb_path.write_text(run_batch, encoding="utf-8", newline="\n")
        changes.append("run_batch.sh")

    task_toml = task_dir / "task.toml"
    milestones = len(list((task_dir / "steps").glob("milestone_*")))
    new_toml = build_task_toml(task_toml.read_text(encoding="utf-8"), milestones)
    if task_toml.read_text(encoding="utf-8").replace("\r\n", "\n") != new_toml:
        task_toml.write_text(new_toml, encoding="utf-8", newline="\n")
        changes.append("task.toml")

    for milestone in sorted((task_dir / "steps").glob("milestone_*")):
        test_py = next(milestone.glob("tests/test_m*.py"), None)
        if not test_py:
            continue
        test_file = test_py.name
        test_sh_path = milestone / "tests" / "test.sh"
        content = TEST_SH.format(test_file=test_file)
        if test_sh_path.read_text(encoding="utf-8").replace("\r\n", "\n") != content:
            test_sh_path.write_text(content, encoding="utf-8", newline="\n")
            changes.append(f"{milestone.name}/tests/test.sh")

    for sh in task_dir.rglob("*.sh"):
        text = sh.read_text(encoding="utf-8")
        if "\r\n" in text or text.endswith("\r"):
            sh.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")

    return changes


def main() -> int:
    updated = 0
    for task_dir in sorted(ROOT.glob("ruby-*")):
        if not task_dir.is_dir() or not (task_dir / "task.toml").is_file():
            continue
        changes = normalize_task(task_dir)
        if changes:
            updated += 1
            print(f"{task_dir.name}: {', '.join(changes)}")
    print(f"Normalized {updated} ruby task(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
