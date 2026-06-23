#!/usr/bin/env python3
"""Apply batch custom-revision fixes across revision queue tasks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_fix_task_toml_timeouts import fix_task_toml  # noqa: E402
from fix_rubric_scores import fix_rubric  # noqa: E402
from revision_batch_orchestrator import fix_test_sh_exit_code, trim_tags  # noqa: E402

# 46 manifest + 3 extra
EXTRA = [
    "go-conference-sponsor-rebate-matcher",
    "cobol-vendor-return-settlement",
    "go-marketplace-payout-matcher",
    "ruby-courier-cod-remittance-reconciler",
    "go-datacenter-rack-hold-release",
    "go-property-lease-deposit-reconciler",
    "go-childcare-attendance-refund-matcher",
]

DELETE_CROSS_SOLVE: dict[str, list[str]] = {}


def all_tasks() -> list[str]:
    from revision_manifest_tasks import load_manifest

    seen: set[str] = set()
    out: list[str] = []
    for _, folder in load_manifest():
        if folder not in seen:
            seen.add(folder)
            out.append(folder)
    for f in EXTRA:
        if f not in seen and (ROOT / f).is_dir():
            out.append(f)
    return sorted(out)


def strip_tool_specific(toml_path: Path) -> bool:
    text = toml_path.read_text(encoding="utf-8")
    new = re.sub(r'subcategories\s*=\s*\["tool_specific"\]\s*\n', "subcategories = []\n", text)
    new = re.sub(r'subcategories\s*=\s*\[[^\]]*"tool_specific"[^\]]*\]', "subcategories = []", new)
    if new != text:
        toml_path.write_text(new, encoding="utf-8")
        return True
    return False


def bump_go_build_timeout(toml_path: Path) -> bool:
    if not toml_path.parent.name.startswith("go-"):
        return False
    text = toml_path.read_text(encoding="utf-8")
    new = re.sub(r"build_timeout_sec\s*=\s*900\.0", "build_timeout_sec = 1200.0", text)
    if new != text:
        toml_path.write_text(new, encoding="utf-8")
        return True
    return False


def ensure_rubric_agent_prefix(rubric: Path) -> bool:
    lines = rubric.read_text(encoding="utf-8").splitlines()
    out = []
    changed = False
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#") and not s.lower().startswith("agent"):
            out.append("Agent " + s[0].lower() + s[1:] if s else s)
            changed = True
        else:
            out.append(ln.rstrip())
    if changed:
        rubric.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return changed


def add_pwd_guard(test_sh: Path) -> bool:
    text = test_sh.read_text(encoding="utf-8")
    guard = """if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi"""
    if guard in text:
        return False
    if "set -uo pipefail" in text:
        text = text.replace(
            "set -uo pipefail\n",
            "set -uo pipefail\n" + guard + "\n\n",
            1,
        )
        test_sh.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    for folder in all_tasks():
        td = ROOT / folder
        if not td.is_dir():
            continue
        changes: list[str] = []
        for rel in DELETE_CROSS_SOLVE.get(folder, []):
            p = td / rel
            if p.is_file():
                p.unlink()
                changes.append(f"deleted {rel}")
        toml = td / "task.toml"
        if toml.is_file():
            if strip_tool_specific(toml):
                changes.append("removed tool_specific")
            if bump_go_build_timeout(toml):
                changes.append("build_timeout 1200")
            if fix_task_toml(toml):
                changes.append("task.toml")
        n = fix_test_sh_exit_code(td)
        if n:
            changes.append(f"test.sh x{n}")
        pwd_n = sum(1 for ts in td.rglob("tests/test.sh") if add_pwd_guard(ts))
        if pwd_n:
            changes.append(f"pwd_guard x{pwd_n}")
        if trim_tags(td):
            changes.append("tags")
        rp = td / "rubric.txt"
        if rp.is_file():
            if fix_rubric(rp):
                changes.append("rubric scores")
            if ensure_rubric_agent_prefix(rp):
                changes.append("rubric Agent prefix")
        if changes:
            print(f"{folder}: {', '.join(changes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
