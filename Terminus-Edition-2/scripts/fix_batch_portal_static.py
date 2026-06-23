#!/usr/bin/env python3
"""Apply portal static-check fixes to the 11 batch-quality tasks."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TASKS = [
    "aws-lambda-event-source-mapping-recovery",
    "cobol-catastrophic-claim-disbursement-router",
    "cobol-retroactive-payroll-adjustment-engine",
    "cobol-db2-financial-master-bulk-update",
    "k8s-networkpolicy-egress-recovery",
    "jenkins-release-pipeline-promotion",
    "k8s-document-renderer-rollout",
    "prometheus-edge-gateway-monitoring",
    "terraform-state-lock-contention",
    "docker-edge-proxy-deployment-recovery",
    "docker-compose-cache-backed-api-recovery",
]

ECR_PYTHON = (
    "public.ecr.aws/docker/library/python:3.13-slim-bookworm"
    "@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb"
)
ECR_DEBIAN = (
    "public.ecr.aws/docker/library/debian:bookworm-slim"
    "@sha256:4724b8cc51e33e398f0e2e15e18d5ec2851ff0c2280647e1310bc1642182655d"
)

DOCKERIGNORE = """.git
.gitignore
**/__pycache__/
**/*.pyc
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/node_modules/
steps/
solution/
tests/
rubric.txt
*.zip
"""

TEST_SH_TEMPLATE = """#!/bin/bash
# Omit -e so pytest failures reach the reward if/else block below.
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m{M}.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""

LOCK_PYTEST = ROOT / "cobol-statement-merge-control-totals" / "environment" / "requirements.lock"
LOCK_PYTEST_CTRF = LOCK_PYTEST  # includes pytest-json-ctrf
LOCK_PYTEST_YAML = ROOT / "k8s-invoice-batch-rbac-recovery" / "environment" / "requirements.lock"

SUBCATEGORY_FIXES = {
    "aws-lambda-event-source-mapping-recovery": 'subcategories = ["api_integration", "tool_specific"]',
    "cobol-db2-financial-master-bulk-update": 'subcategories = ["tool_specific", "db_interaction"]',
    "prometheus-edge-gateway-monitoring": 'subcategories = ["tool_specific"]',
    "terraform-state-lock-contention": 'subcategories = ["tool_specific"]',
    "docker-edge-proxy-deployment-recovery": 'subcategories = ["tool_specific"]',
    "docker-compose-cache-backed-api-recovery": 'subcategories = ["tool_specific"]',
}


def write_test_sh(task_dir: Path) -> int:
    n = 0
    for m in range(1, 20):
        test_dir = task_dir / f"steps/milestone_{m}/tests"
        test_sh = test_dir / "test.sh"
        if not test_sh.is_file():
            break
        py_files = list(test_dir.glob("test_m*.py"))
        if not py_files:
            continue
        match = re.search(r"test_m(\d+)", py_files[0].name)
        if not match:
            continue
        content = TEST_SH_TEMPLATE.format(M=match.group(1))
        if test_sh.read_text(encoding="utf-8") != content:
            test_sh.write_text(content, encoding="utf-8")
            n += 1
    return n


def write_dockerignore(env_dir: Path) -> bool:
    path = env_dir / ".dockerignore"
    if path.read_text(encoding="utf-8") == DOCKERIGNORE if path.exists() else False:
        return False
    path.write_text(DOCKERIGNORE, encoding="utf-8")
    return True


def copy_lock(env_dir: Path, variant: str) -> bool:
    src = {
        "pytest": LOCK_PYTEST,
        "pytest_ctrf": LOCK_PYTEST_CTRF,
        "pytest_yaml": LOCK_PYTEST_YAML,
    }[variant]
    dst = env_dir / "requirements.lock"
    if dst.exists() and dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8"):
        return False
    shutil.copy2(src, dst)
    return True


def fix_task_toml(task_dir: Path) -> bool:
    name = task_dir.name
    if name not in SUBCATEGORY_FIXES:
        return False
    path = task_dir / "task.toml"
    text = path.read_text(encoding="utf-8")
    new_line = SUBCATEGORY_FIXES[name]
    updated = re.sub(r"^subcategories\s*=\s*\[.*\]\s*$", new_line, text, count=1, flags=re.M)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def fix_aws_lambda_m2_import(task_dir: Path) -> bool:
    path = task_dir / "steps/milestone_2/tests/test_m2.py"
    text = path.read_text(encoding="utf-8")
    import_line = "from src.iam_simulator import decide, has_broad_sqs_grant, has_log_permissions, required_sqs_decisions\n"
    if import_line not in text:
        return False
    text = text.replace(import_line, "")
    marker = "PYTHON = sys.executable\n\n"
    if marker not in text:
        return False
    replacement = marker + import_line
    if text.count(import_line) > 0:
        return False
    updated = text.replace(marker, replacement, 1)
    # remove duplicate if still at old location
    parts = updated.split("\n\nclass TestMilestone2:")
    if len(parts) == 2 and import_line in parts[0]:
        body = parts[0]
        body = body.replace("\n" + import_line.rstrip("\n"), "", 1)
        updated = body + "\n\nclass TestMilestone2:" + parts[1]
    path.write_text(updated, encoding="utf-8")
    return True


def pip_install_block() -> str:
    return """COPY requirements.lock /tmp/requirements.lock
RUN pip3 install --no-cache-dir --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \\
    && rm -f /tmp/requirements.lock
"""


def write_dockerfiles() -> None:
    # aws-lambda: selective COPY
    (ROOT / "aws-lambda-event-source-mapping-recovery/environment/Dockerfile").write_text(
        f"""FROM {ECR_PYTHON}

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    APP_ROOT=/app \\
    PYTHONPATH=/app

{pip_install_block()}
WORKDIR /app

COPY config/ /app/config/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY evidence/ /app/evidence/
COPY fixtures/ /app/fixtures/
COPY ops/ /app/ops/
COPY observability/ /app/observability/
COPY runbooks/ /app/runbooks/
COPY scripts/ /app/scripts/
COPY src/ /app/src/
COPY tests_support/ /app/tests_support/

RUN chmod +x /app/scripts/*.py /app/scripts/*.sh && mkdir -p /logs/verifier /app/tmp
""",
        encoding="utf-8",
    )

    # cobol-catastrophic: debian + gnucobol
    (ROOT / "cobol-catastrophic-claim-disbursement-router/environment/Dockerfile").write_text(
        f"""FROM {ECR_DEBIAN}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        bash \\
        ca-certificates \\
        gnucobol3 \\
        python3 \\
        python3-pip \\
    && rm -rf /var/lib/apt/lists/*

{pip_install_block()}
WORKDIR /app
COPY . /app
RUN mkdir -p /app/out /app/build /logs/verifier
""",
        encoding="utf-8",
    )

    python_simple = f"""FROM {ECR_PYTHON}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        bash \\
        ca-certificates \\
        coreutils \\
        findutils \\
        grep \\
        sed \\
        gawk \\
    && rm -rf /var/lib/apt/lists/*

{pip_install_block()}
WORKDIR /app
COPY . /app
RUN mkdir -p /app/out /logs/verifier
"""

    for task in [
        "cobol-retroactive-payroll-adjustment-engine",
        "jenkins-release-pipeline-promotion",
        "k8s-document-renderer-rollout",
        "prometheus-edge-gateway-monitoring",
        "terraform-state-lock-contention",
        "docker-edge-proxy-deployment-recovery",
        "docker-compose-cache-backed-api-recovery",
    ]:
        (ROOT / task / "environment/Dockerfile").write_text(python_simple, encoding="utf-8")

    # k8s-networkpolicy with yaml in lock
    (ROOT / "k8s-networkpolicy-egress-recovery/environment/Dockerfile").write_text(
        python_simple,
        encoding="utf-8",
    )

    # cobol-db2 with gnucobol
    (ROOT / "cobol-db2-financial-master-bulk-update/environment/Dockerfile").write_text(
        f"""FROM {ECR_PYTHON}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        bash \\
        ca-certificates \\
        coreutils \\
        diffutils \\
        gnucobol \\
    && rm -rf /var/lib/apt/lists/*

{pip_install_block()}
WORKDIR /app
COPY . /app
RUN chmod +x /app/bin/run_finbulk.sh /app/scripts/reset_lab.sh /app/tools/*.py \\
    && mkdir -p /app/out /logs/verifier
""",
        encoding="utf-8",
    )


def main() -> None:
    write_dockerfiles()
    for task in TASKS:
        task_dir = ROOT / task
        env_dir = task_dir / "environment"
        n_test = write_test_sh(task_dir)
        ign = write_dockerignore(env_dir)
        lock_variant = "pytest_yaml" if task == "k8s-networkpolicy-egress-recovery" else "pytest_ctrf"
        lock = copy_lock(env_dir, lock_variant)
        toml = fix_task_toml(task_dir)
        m2 = fix_aws_lambda_m2_import(task_dir) if task == "aws-lambda-event-source-mapping-recovery" else False
        print(
            f"{task}: test.sh={n_test} dockerignore={ign} lock={lock} toml={toml} m2import={m2}"
        )


if __name__ == "__main__":
    main()
