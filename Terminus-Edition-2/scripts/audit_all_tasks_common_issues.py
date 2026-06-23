#!/usr/bin/env python3
"""Audit (and optionally fix) common Terminus Edition 2 task issues across all task folders."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "all_tasks_common_issue_audit_20260529.txt"

sys.path.insert(0, str(ROOT / "scripts"))
from audit_fix_task_toml_timeouts import audit_only, fix_task_toml  # noqa: E402
from preflight_task import run_preflight  # noqa: E402


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def fix_protect_placeholders(text: str) -> str:
    text = re.sub(r"__PROTECT_\w+__", "INVOICES", text)
    text = re.sub(r"^@@\w+@@ = APP", "INVOICES = APP", text, flags=re.M)
    text = text.replace("@@ROW_FIXTURE_A@@", "INVOICES")
    text = text.replace("@@ROW_FIXTURE_B@@", "PAYMENTS")
    text = re.sub(r"@@\w+@@", "INVOICES", text)
    return text


def audit_task(task_dir: Path, fix: bool) -> list[str]:
    issues: list[str] = []

    toml = task_dir / "task.toml"
    if not toml.is_file():
        issues.append("missing task.toml")
    else:
        probs = audit_only(toml)
        if probs:
            issues.append(f"task.toml: {', '.join(probs)}")
            if fix:
                fix_task_toml(toml)

    docker = task_dir / "environment" / "Dockerfile"
    if docker.is_file():
        d = docker.read_text(encoding="utf-8", errors="ignore")
        if "tmux" not in d:
            issues.append("Dockerfile missing tmux")
        if re.search(r"--platform\s*=\s*linux/amd64", d, re.I):
            issues.append("Dockerfile hardcodes --platform=linux/amd64")
        if re.search(r"\\\\\s*\\\\", d):
            issues.append("Dockerfile malformed apt continuation")
        if not re.search(r"^FROM\s+\S+@sha256:[0-9a-f]{64}", d, re.M):
            issues.append("Dockerfile missing digest-pinned FROM")
    else:
        issues.append("missing environment/Dockerfile")

    if not (task_dir / "environment" / ".dockerignore").is_file():
        issues.append("missing environment/.dockerignore")

    for sh in task_dir.rglob("*.sh"):
        try:
            raw = sh.read_bytes()
        except OSError:
            continue
        if b"\r" in raw:
            issues.append(f"CRLF in {sh.relative_to(task_dir).as_posix()}")
            if fix:
                write_lf(sh, raw.decode("utf-8", errors="ignore"))

    for solve in task_dir.rglob("solve*.sh"):
        text = solve.read_text(encoding="utf-8", errors="ignore")
        if re.search(
            r"\.\./milestone_|/app/steps/milestone_|/steps/milestone_|"
            r"\$STEPS_DIR/milestone_|\$steps_dir/milestone_",
            text,
        ):
            rel = solve.relative_to(task_dir).as_posix()
            issues.append(f"cross-milestone solve path in {rel}")
        if "func allowedPassType" in text and "{\\\\n" in text:
            rel = solve.relative_to(task_dir).as_posix()
            issues.append(f"broken literal \\\\n in solve patch {rel}")

    rubric = task_dir / "rubric.txt"
    if rubric.is_file() and (task_dir / "steps" / "milestone_2").is_dir():
        r = rubric.read_text(encoding="utf-8", errors="ignore")
        if "# Rubric 1" not in r:
            issues.append("rubric.txt missing # Rubric 1/2/3 milestone blocks")

    m1 = task_dir / "steps" / "milestone_1" / "instruction.md"
    if m1.is_file():
        t = m1.read_text(encoding="utf-8", errors="ignore").lower()
        if not any(
            x in t
            for x in ("blank", "empty string", "two consecutive commas", "leave `")
        ):
            issues.append("milestone_1 instruction missing blank-unmatched category rule")

    m3_test = task_dir / "steps" / "milestone_3" / "tests" / "test_m3.py"
    if m3_test.is_file():
        t = m3_test.read_text(encoding="utf-8", errors="ignore")
        if "test_latest" not in t and "latest_" not in t:
            issues.append("milestone_3 missing latest-date anti-first-fit test")

    for test_py in task_dir.rglob("test_m*.py"):
        text = test_py.read_text(encoding="utf-8", errors="ignore")
        if "__PROTECT_" in text or "@@PYTEST_" in text or "@@FIXTURE_" in text:
            rel = test_py.relative_to(task_dir).as_posix()
            issues.append(f"scaffold placeholder leaked in {rel}")
            if fix:
                test_py.write_text(fix_protect_placeholders(text), encoding="utf-8")

    main_go = task_dir / "environment" / "cmd" / "reconcile" / "main.go"
    m1_test = task_dir / "steps" / "milestone_1" / "tests" / "test_m1.py"
    if main_go.is_file() and m1_test.is_file():
        go = main_go.read_text(encoding="utf-8", errors="ignore")
        m1_text = m1_test.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'SUMMARY\s*=\s*APP\s*/\s*"out"\s*/\s*"([^"]+)"', m1_text)
        if m:
            expected = m.group(1)
            if f"/app/out/{expected}" not in go and "credit_summary.json" in go:
                issues.append(
                    f"main.go writes credit_summary.json but tests expect {expected}"
                )

    for test_sh in task_dir.rglob("tests/test.sh"):
        ts = test_sh.read_text(encoding="utf-8", errors="ignore")
        if "-rA" not in ts:
            issues.append(f"test.sh missing pytest -rA in {test_sh.parent.parent.name}")

    for inst in task_dir.rglob("instruction.md"):
        text = inst.read_text(encoding="utf-8", errors="ignore")
        if "/app/out/report.csv" in text or "/app/out/summary.txt" in text:
            rel = inst.relative_to(task_dir).as_posix()
            issues.append(f"generic output path in {rel}")

    return issues


def main() -> int:
    fix = "--fix" in sys.argv
    run_preflight_all = "--preflight" in sys.argv
    tasks = sorted(p.parent for p in ROOT.glob("*/task.toml"))
    by_issue: dict[str, list[str]] = defaultdict(list)

    for task_dir in tasks:
        for issue in audit_task(task_dir, fix=fix):
            by_issue[issue].append(task_dir.name)

    preflight_fail: list[str] = []
    if run_preflight_all:
        for task_dir in tasks:
            if run_preflight(task_dir) != 0:
                preflight_fail.append(task_dir.name)

    affected = {n for names in by_issue.values() for n in names}
    lines = [
        f"Common-issue audit for {len(tasks)} task folders",
        f"Mode: {'fix+audit' if fix else 'audit-only'}",
        "",
    ]
    for issue, names in sorted(by_issue.items(), key=lambda x: (-len(x[1]), x[0])):
        lines.append(f"[{len(names)}] {issue}")
        for n in sorted(names)[:30]:
            lines.append(f"  - {n}")
        if len(names) > 30:
            lines.append(f"  ... and {len(names) - 30} more")
        lines.append("")

    if preflight_fail:
        lines.append(f"Preflight failures ({len(preflight_fail)}):")
        for n in preflight_fail:
            lines.append(f"  - {n}")
        lines.append("")

    lines.append(f"Tasks with zero reported issues: {len(tasks) - len(affected)}/{len(tasks)}")
    lines.append("")
    lines.append("Run: python scripts/audit_all_tasks_common_issues.py --fix")
    lines.append("Run: python scripts/audit_fix_task_toml_timeouts.py")
    lines.append("Run: python scripts/audit_all_tasks_common_issues.py --preflight")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))
    return 1 if (by_issue or preflight_fail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
