#!/usr/bin/env python3
"""Audit template standards for tasks listed in new_tasks.txt."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "new_tasks.txt"

sys.path.insert(0, str(ROOT / "scripts"))
from audit_all_tasks_common_issues import audit_task  # noqa: E402
from audit_fix_task_toml_timeouts import audit_only  # noqa: E402
from preflight_task import run_preflight  # noqa: E402


def load_tasks() -> list[str]:
    names: list[str] = []
    raw = LIST.read_text(encoding="utf-8-sig")
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def test_sh_reward_ok(text: str) -> bool:
    return (
        "python3 -m pytest" in text
        and "if [ $? -eq 0 ]; then" in text
        and "echo 1 > /logs/verifier/reward.txt" in text
        and "echo 0 > /logs/verifier/reward.txt" in text
    )


def extra_checks(task_dir: Path) -> list[str]:
    issues: list[str] = []
    toml = task_dir / "task.toml"
    if toml.is_file():
        text = toml.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r"^\[agent\]", text, re.M):
            issues.append("task.toml missing top-level [agent]")
        if not re.search(r"^\[verifier\]", text, re.M):
            issues.append("task.toml missing top-level [verifier]")
        if re.search(r"^\[agent\].*\[agent\]", text, re.S):
            issues.append("task.toml duplicate [agent] sections")
        if re.search(r"build_timeout_sec\s*=", text) and len(re.findall(r"build_timeout_sec\s*=", text)) > 1:
            issues.append("task.toml duplicate build_timeout_sec")

    for test_sh in task_dir.rglob("tests/test.sh"):
        ts = test_sh.read_text(encoding="utf-8", errors="ignore")
        if not test_sh_reward_ok(ts):
            rel = test_sh.relative_to(task_dir).as_posix()
            issues.append(f"test.sh missing if-pytest reward pattern in {rel}")

    m1 = task_dir / "steps" / "milestone_1" / "instruction.md"
    m2 = task_dir / "steps" / "milestone_2" / "instruction.md"
    m3 = task_dir / "steps" / "milestone_3" / "instruction.md"
    m1_test = task_dir / "steps" / "milestone_1" / "tests" / "test_m1.py"
    if m1.is_file() and m1_test.is_file():
        inst = m1.read_text(encoding="utf-8", errors="ignore")
        test = m1_test.read_text(encoding="utf-8", errors="ignore")
        for pat in (
            r'REPORT\s*=\s*APP\s*/\s*"out"\s*/\s*"([^"]+)"',
            r'SUMMARY\s*=\s*APP\s*/\s*"out"\s*/\s*"([^"]+)"',
        ):
            for m in re.finditer(pat, test):
                name = m.group(1)
                if f"/app/out/{name}" not in inst and name not in inst:
                    issues.append(f"milestone_1 instruction missing output path {name}")

    if m2.is_file():
        t = m2.read_text(encoding="utf-8", errors="ignore")
        if "MEDICAL`, `CUSTOMS`, or `MEDICAL`" in t or "MEDICAL`, `CUSTOMS`, or `MEDICAL`" in t:
            issues.append("milestone_2 instruction duplicate MEDICAL in eligible types")

    rubric = task_dir / "rubric.txt"
    if rubric.is_file() and (task_dir / "steps" / "milestone_2").is_dir():
        r = rubric.read_text(encoding="utf-8", errors="ignore")
        for block in ("# Rubric 1", "# Rubric 2", "# Rubric 3"):
            if block not in r:
                issues.append(f"rubric.txt missing {block}")

    # Hold-release / realtime: M1 instruction should not require windows if tests omit them
    if (task_dir / "environment" / "cmd" / "reconcile" / "main.go").is_file():
        m1_inst = m1.read_text(encoding="utf-8", errors="ignore") if m1.is_file() else ""
        if "windows.csv" in m1_inst.lower() and "milestone 1" in m1_inst.lower():
            if "release_ts` is on or after" in m1_inst and "window" in m1_inst.lower()[:800]:
                pass  # ok if both mentioned
        m3_test = task_dir / "steps" / "milestone_3" / "tests" / "test_m3.py"
        if m3_test.is_file():
            t3 = m3_test.read_text(encoding="utf-8", errors="ignore")
            if "test_latest" not in t3 and "latest_" not in t3 and "tie" not in t3.lower():
                issues.append("milestone_3 missing latest-ts tie-break test")

    if (task_dir / "environment" / "app" / "reconcile.rb").is_file():
        data = task_dir / "environment" / "data"
        if data.is_dir():
            wrong = [p.name for p in data.iterdir() if p.name in ("sessions.csv", "adjustments.csv")]
            if wrong:
                issues.append(f"environment/data still has template filenames: {', '.join(wrong)}")

    if (task_dir / "environment" / "data" / "dock_fees.dat").is_file():
        issues.append("environment/data still has template dock_fees.dat")

    return issues


def main() -> int:
    tasks = load_tasks()
    report_path = ROOT / ".terminus_logs" / "new_tasks_audit_latest.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    by_task: dict[str, list[str]] = {}
    by_issue: dict[str, list[str]] = defaultdict(list)
    preflight_fail: list[str] = []

    for name in tasks:
        task_dir = ROOT / name
        if not task_dir.is_dir():
            by_task[name] = [f"task directory not found: {task_dir}"]
            by_issue["task directory not found"].append(name)
            continue
        issues: list[str] = []
        if run_preflight(task_dir) != 0:
            preflight_fail.append(name)
            issues.append("preflight failed (see errors above)")
        issues.extend(audit_task(task_dir, fix=False))
        issues.extend(extra_checks(task_dir))
        # dedupe preserving order
        seen: set[str] = set()
        uniq = []
        for i in issues:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        if uniq:
            by_task[name] = uniq
            for i in uniq:
                by_issue[i].append(name)

    lines = [
        f"New tasks audit ({len(tasks)} tasks from new_tasks.txt)",
        "",
    ]
    if preflight_fail:
        lines.append(f"Preflight failures: {len(preflight_fail)}")
        for n in preflight_fail:
            lines.append(f"  - {n}")
        lines.append("")

    clean = [n for n in tasks if n not in by_task]
    lines.append(f"Clean: {len(clean)}/{len(tasks)}")
    if clean:
        lines.append("  " + ", ".join(clean))
    lines.append("")

    if by_issue:
        lines.append("Issues by category:")
        for issue, names in sorted(by_issue.items(), key=lambda x: (-len(x[1]), x[0])):
            lines.append(f"[{len(names)}] {issue}")
            for n in sorted(names):
                lines.append(f"  - {n}")
            lines.append("")

    if by_task:
        lines.append("Per-task summary:")
        for name in tasks:
            if name in by_task:
                lines.append(f"{name}:")
                for i in by_task[name]:
                    lines.append(f"  - {i}")
        lines.append("")

    report = "\n".join(lines)
    report_path.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nReport: {report_path}")
    return 1 if by_task or preflight_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
