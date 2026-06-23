#!/usr/bin/env python3
"""Local structural scan of all revision-queue task folders."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}


def folders() -> list[str]:
    out: set[str] = set()
    for p in (ROOT / "needs_revision_mapped.txt", ROOT / "batch11_submission_map.txt"):
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and not parts[0].startswith("#"):
                name = parts[1]
                out.add(ALIASES.get(name, name))
    return sorted(out)


def scan(name: str) -> dict:
    td = ROOT / name
    r: dict = {"folder": name, "issues": []}
    if not td.is_dir():
        r["issues"].append("missing_folder")
        return r
    t = (td / "task.toml").read_text(encoding="utf-8")
    if not re.search(r"^\[agent\]", t, re.M):
        r["issues"].append("missing_root_agent")
    if not re.search(r"^\[verifier\]", t, re.M):
        r["issues"].append("missing_root_verifier")
    bt = re.search(r"build_timeout_sec\s*=\s*([\d.]+)", t)
    if bt and float(bt.group(1)) < 1200:
        r["issues"].append(f"build_timeout={bt.group(1)}")
    df = td / "environment/Dockerfile"
    if df.is_file():
        d = df.read_text(encoding="utf-8")
        if d.startswith("FROM golang:"):
            r["issues"].append("dockerfile_golang_full_image")
        if "/opt/verifier" in d and "pip3 install --break-system-packages pytest" not in d:
            r["issues"].append("dockerfile_venv_pytest")
    for sh in td.glob("steps/milestone_*/tests/test.sh"):
        c = sh.read_text(encoding="utf-8")
        if "if python3 -m pytest" in c and "; then" in c:
            r["issues"].append(f"bad_test_sh:{sh.name}")
        if "set -euo pipefail" in c:
            r["issues"].append(f"test_sh_set_e:{sh.parent.parent.name}")
    if list(td.glob("scripts/*.py")):
        r["issues"].append("task_scripts_py")
    return r


def main() -> None:
    rows = [scan(f) for f in folders()]
    clean = [r for r in rows if not r["issues"]]
    fix = [r for r in rows if r["issues"]]
    out = ROOT / "Revision-ChatGpt" / "revision_local_scan.md"
    lines = ["# Local scan — revision queue tasks\n\n", f"Total: {len(rows)} | Clean: {len(clean)} | Needs local fix: {len(fix)}\n\n"]
    lines.append("## Needs local fix\n\n| Task | Issues |\n|------|--------|\n")
    for r in fix:
        lines.append(f"| {r['folder']} | {', '.join(r['issues'])} |\n")
    lines.append("\n## Clean (leave for rubric + resubmit)\n\n")
    for r in clean:
        lines.append(f"- {r['folder']}\n")
    out.write_text("".join(lines), encoding="utf-8")
    print(out)
    print(f"clean={len(clean)} fix={len(fix)}")


if __name__ == "__main__":
    main()
