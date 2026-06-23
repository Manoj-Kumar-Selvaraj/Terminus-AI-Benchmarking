#!/usr/bin/env python3
"""Split semicolon-separated Python statements to satisfy ruff E702."""
from __future__ import annotations

import re
import tokenize
from io import StringIO
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


def split_statement_semicolons(line: str) -> list[str]:
    """Split a line on semicolons that separate statements, not string contents."""
    stripped = line.rstrip("\n\r")
    prefix = re.match(r"^(\s*)", stripped).group(1)
    body = stripped[len(prefix) :]
    if not body or body.startswith("#"):
        return [line]

    try:
        tokens = list(tokenize.generate_tokens(StringIO(body).readline))
    except tokenize.TokenError:
        return [line]

    parts: list[str] = []
    current: list[str] = []
    for tok in tokens:
        if tok.type == tokenize.OP and tok.string == ";":
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(tok.string)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    if len(parts) <= 1:
        return [line]

    suffix = "\n" if line.endswith("\n") else ""
    return [f"{prefix}{part}{suffix}" for part in parts]


def split_semicolon_lines(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        out.extend(split_statement_semicolons(line))
    return "".join(out)


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = split_semicolon_lines(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    total = 0
    for task in TASKS:
        task_dir = ROOT / task
        for path in task_dir.rglob("*.py"):
            if fix_file(path):
                print(f"fixed {path.relative_to(ROOT)}")
                total += 1
    print(f"done, {total} files updated")


if __name__ == "__main__":
    main()
