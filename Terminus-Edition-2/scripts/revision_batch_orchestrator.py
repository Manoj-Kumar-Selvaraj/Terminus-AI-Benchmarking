#!/usr/bin/env python3
"""Revision batch orchestrator: fetch feedback, audit, fix common issues, pack zips."""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "Revision-ChatGpt" / "needs_revision_pulls" / "portal_ids_manifest.tsv"
FB_DIR = ROOT / "Revision-ChatGpt" / "portal_feedback"
OUT_DIR = ROOT / "revision-batch-upload"
LOG_DIR = ROOT / "Revision-ChatGpt" / "revision_batch_logs"
REPORT = ROOT / "Revision-ChatGpt" / "revision_batch_master_report.md"

sys.path.insert(0, str(ROOT / "scripts"))
from audit_fix_task_toml_timeouts import audit_only, fix_task_toml  # noqa: E402
from revision_manifest_tasks import load_manifest  # noqa: E402


def unique_folders() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _, folder in load_manifest():
        if folder not in seen:
            seen.add(folder)
            out.append(folder)
    return sorted(out)


def feedback_path(sid: str) -> Path | None:
    candidates = sorted(FB_DIR.glob(f"audit_{sid}*"))
    if candidates:
        return candidates[0]
    candidates = sorted(FB_DIR.glob(f"full_feedback_{sid}*"))
    if candidates:
        return candidates[0]
    return None


def parse_notes(text: str) -> dict:
    out: dict = {
        "revision_notes": "",
        "difficulty": "",
        "quality_fails": [],
        "agent_warnings": [],
        "agent_critical": [],
        "agent_suggestions": [],
        "instr_sufficiency": "",
        "autoeval": "",
    }
    m = re.search(
        r"Revision Notes\s*-+\s*(.*?)(?=\n(?:Rebuttal Notes|Summary \(difficulty|Quality check|Agent review|\Z))",
        text,
        re.S,
    )
    if m:
        out["revision_notes"] = m.group(1).strip()[:500]
    m = re.search(r"Difficulty:\s*(.+)", text)
    if m:
        out["difficulty"] = m.group(1).strip()
    m = re.search(r"AutoEval Execution Summary:\s*(.+)", text)
    if m:
        out["autoeval"] = m.group(1).strip()[:200]
    for line in text.splitlines():
        if "❌ fail" in line or "FAIL" in line and "Quality" in text[: text.find(line)]:
            if "pass -" not in line:
                out["quality_fails"].append(line.strip())
    m = re.search(r"Task Instruction Sufficiency:\s*(.+)", text)
    if m:
        out["instr_sufficiency"] = m.group(1).strip()
    ar = re.search(r"Agent review\s*-+\s*(.*?)(?=\n={3,}|\Z)", text, re.S)
    if not ar:
        ar = re.search(r"=== agent_review\.txt ===\s*(.*)", text, re.S)
    if ar:
        body = ar.group(1)
        for line in body.splitlines():
            u = line.upper()
            if "WARNING" in u or "⚠" in line:
                out["agent_warnings"].append(line.strip())
            if "CRITICAL" in u or "🔴" in line:
                out["agent_critical"].append(line.strip())
            if "SUGGESTION" in u or "💡" in line:
                out["agent_suggestions"].append(line.strip())
    return out


def fix_test_sh_exit_code(task_dir: Path) -> int:
    """Use exit_code=$? pattern instead of bare $? after if."""
    n = 0
    for m in range(1, 20):
        p = task_dir / f"steps/milestone_{m}/tests/test.sh"
        if not p.is_file():
            break
        text = p.read_text(encoding="utf-8")
        if "exit_code=$?" in text:
            continue
        if "python3 -m pytest" not in text and "ruby" not in text:
            continue
        new = text
        new = re.sub(
            r"python3 -m pytest[^\n]+\n\nif \[ \$\? -eq 0 \]",
            lambda m: m.group(0).replace(
                "if [ $? -eq 0 ]",
                "exit_code=$?\n\nif [ $exit_code -eq 0 ]",
            ),
            new,
            count=1,
        )
        if new != text:
            p.write_text(new, encoding="utf-8")
            n += 1
    return n


def trim_tags(task_dir: Path) -> bool:
    toml = task_dir / "task.toml"
    if not toml.is_file():
        return False
    text = toml.read_text(encoding="utf-8")
    m = re.search(r"^tags = \[(.*?)\]", text, re.MULTILINE)
    if not m:
        return False
    tags = [t.strip().strip('"').strip("'") for t in m.group(1).split(",") if t.strip()]
    drop = {"data-processing", "data_processing"}
    new_tags = [t for t in tags if t not in drop][:6]
    if new_tags == tags:
        return False
    quoted = ", ".join(f'"{t}"' for t in new_tags)
    toml.write_text(text[: m.start(1)] + quoted + text[m.end(1) :], encoding="utf-8")
    return True


def apply_common_fixes(folder: str) -> list[str]:
    td = ROOT / folder
    fixes: list[str] = []
    if not td.is_dir():
        return ["MISSING_FOLDER"]
    if fix_task_toml(td / "task.toml"):
        fixes.append("task.toml")
    probs = audit_only(td / "task.toml")
    if probs:
        fixes.append(f"task.toml still: {', '.join(probs)}")
    n = fix_test_sh_exit_code(td)
    if n:
        fixes.append(f"test.sh exit_code x{n}")
    if trim_tags(td):
        fixes.append("tags trimmed")
    return fixes


def fetch_feedback(sid: str) -> bool:
    stb = "/root/.local/bin/stb"
    try:
        subprocess.run(
            [stb, "submissions", "feedback", sid],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    import glob

    pattern = f"/tmp/feedback_{sid}_*"
    dirs = sorted(glob.glob(pattern), reverse=True)
    if not dirs:
        return False
    latest = Path(dirs[0])
    dest = FB_DIR / f"audit_{sid}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("notes.txt", "agent_review.txt"):
        src = latest / name
        if src.is_file():
            (dest / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return (dest / "notes.txt").is_file()


def pack_zip(folder: str) -> Path | None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_script = ROOT / "scripts" / "zip.sh"
    dest = OUT_DIR / f"{folder}.zip"
    try:
        subprocess.run(
            ["bash", str(zip_script), "--task", str(ROOT / folder), "--out", str(OUT_DIR), "--zip-name", f"{folder}.zip"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"pack fail {folder}: {e}", file=sys.stderr)
        return None
    return dest if dest.is_file() else None


def build_report(rows: list[dict]) -> str:
    lines = [
        "# Revision batch master report",
        "",
        f"Tasks in scope: {len(rows)} unique folders from portal manifest (LOCAL_OK).",
        "",
        "| Folder | Submission ID | Difficulty | AutoEval | Open issues | Fixes applied | Zip |",
        "|--------|---------------|------------|----------|-------------|---------------|-----|",
    ]
    for r in rows:
        issues = []
        if "TRIVIAL" in r.get("difficulty", "") or "EASY" in r.get("difficulty", ""):
            issues.append("difficulty")
        if "FAILED" in r.get("autoeval", ""):
            issues.append("autoeval")
        if r.get("quality_fails"):
            issues.append("quality")
        if r.get("agent_critical") or r.get("agent_warnings"):
            issues.append("agent")
        if "FAIL" in r.get("instr_sufficiency", ""):
            issues.append("instr")
        if r.get("revision_notes") and "No revision" not in r.get("revision_notes", ""):
            if len(r["revision_notes"]) > 20:
                issues.append("human notes")
        zip_ok = "yes" if r.get("zip") else "no"
        lines.append(
            f"| {r['folder']} | `{r['sid'][:8]}…` | {r.get('difficulty','')[:40]} | "
            f"{'FAIL' if 'FAILED' in r.get('autoeval','') else 'ok'} | "
            f"{', '.join(issues) or '—'} | {', '.join(r.get('fixes',[])) or '—'} | {zip_ok} |"
        )
    lines.append("")
    lines.append(f"Zips output: `{OUT_DIR}`")
    return "\n".join(lines)


def main() -> int:
    fetch = "--fetch" in sys.argv
    pack = "--pack" in sys.argv
    fix = "--fix" in sys.argv or pack

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sid_by_folder: dict[str, str] = {}
    for sid, folder in load_manifest():
        sid_by_folder.setdefault(folder, sid)

    rows: list[dict] = []
    for folder in unique_folders():
        sid = sid_by_folder[folder]
        row: dict = {"folder": folder, "sid": sid, "fixes": []}

        fb = feedback_path(sid)
        if not fb and fetch:
            print(f"fetch {sid} {folder}")
            fetch_feedback(sid)
            fb = feedback_path(sid)
        if fb and (fb / "notes.txt").is_file():
            parsed = parse_notes((fb / "notes.txt").read_text(encoding="utf-8"))
            row.update(parsed)
            if (fb / "agent_review.txt").is_file():
                ar = parse_notes((fb / "agent_review.txt").read_text(encoding="utf-8"))
                row["agent_warnings"] = ar.get("agent_warnings") or row.get("agent_warnings", [])
        else:
            row["revision_notes"] = "NO_FEEDBACK_CACHED"

        if fix:
            row["fixes"] = apply_common_fixes(folder)

        if pack:
            zp = pack_zip(folder)
            row["zip"] = str(zp) if zp else ""

        rows.append(row)
        print(f"{folder}: fixes={row.get('fixes')} zip={'ok' if row.get('zip') else 'skip'}")

    REPORT.write_text(build_report(rows), encoding="utf-8")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
