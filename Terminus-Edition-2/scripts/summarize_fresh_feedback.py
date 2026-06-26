#!/usr/bin/env python3
"""Create a complete revision brief from All-New-Feedbacks/<task>.

The brief is intentionally deterministic and copy-friendly: it collects the
curated fresh report files into one markdown document without truncating
actionable feedback. This keeps the agent prompt focused on one file while
avoiding missed issues from clipped summaries.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_ROOT = Path("All-New-Feedbacks")
REPORT_ORDER = [
    "human_reviewer_feedback.txt",
    "notes.txt",
    "agent_review.txt",
    "task_review_report.txt",
    "test_quality_judge_report.txt",
    "quality_report.txt",
    "difficulty_check_latest.txt",
    "code_quality_check_results.txt",
]

MAX_SECTION_CHARS = 10_000_000

ACTION_PATTERNS = (
    "CRITICAL ISSUES",
    "WARNINGS",
    "SUGGESTIONS",
    "PROBLEM",
    "REQUIRED FIX",
    "SUGGESTED FIX",
    "REVISION NOTES",
    "FAILED",
    "FAIL",
    "VULNERABLE",
    "MISSING",
    "GAP",
    "STATIC CHECK",
    "ORACLE",
    "RUBRIC",
    "INSTRUCTION",
    "INSTRUCTION SUFFICIENCY",
    "TASK INSTRUCTION",
    "TASK-INSTRUCTION",
    "BEHAVIOR_IN_TASK_DESCRIPTION",
    "TASK DESCRIPTION",
    "DOCKER",
    "CATEGORY",
    "HUMAN REVIEWER",
)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return compact


def clean_excerpt(text: str) -> str:
    cleaned: list[str] = []
    for line in normalize_lines(text):
        stripped = line.strip()
        if not stripped:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if stripped.startswith("## "):
            stripped = stripped[3:].strip()
        if re.fullmatch(r"[=\-_*]{20,}", stripped):
            continue
        if stripped.startswith(("â”", "┌", "└", "│", "├", "─")):
            continue
        if "â”" in stripped and len(stripped) > 20:
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned).strip()


def full_report_text(text: str) -> str:
    """Normalize line endings and blank runs while preserving report content."""
    return "\n".join(normalize_lines(text)).strip()


def extract_revision_notes(text: str, max_lines: int = 80) -> str:
    lines = normalize_lines(text)
    if not lines:
        return ""
    out: list[str] = []
    capture = False
    for line in lines:
        upper = line.upper()
        if upper.startswith("REVISION NOTES") or upper.startswith("REBUTTAL NOTES"):
            capture = True
        elif capture and (
            upper.startswith("SUMMARY (")
            or upper.startswith("UNIT TESTS RESULTS")
            or upper.startswith("ANALYSIS ON AGENT FAILURES")
        ):
            capture = False
        if capture:
            out.append(line)
        if capture and len(out) >= max_lines:
            break
    return "\n".join(out).strip()


def extract_difficulty_summary(text: str, max_lines: int = 55) -> str:
    lines = normalize_lines(text)
    out: list[str] = []
    for line in lines:
        upper = line.upper()
        if upper.startswith("UNIT TESTS RESULTS") or upper.startswith("ANALYSIS ON AGENT FAILURES"):
            break
        out.append(line)
        if len(out) >= max_lines:
            break
    summary = "\n".join(out).strip()
    instruction_hits: list[str] = []
    for index, line in enumerate(lines):
        upper = line.upper()
        if any(
            pattern in upper
            for pattern in (
                "TASK INSTRUCTION",
                "INSTRUCTION SUFFICIENCY",
                "BEHAVIOR_IN_TASK_DESCRIPTION",
                "TASK DESCRIPTION",
            )
        ):
            start = max(0, index - 2)
            end = min(len(lines), index + 10)
            chunk = "\n".join(lines[start:end]).strip()
            if chunk and chunk not in instruction_hits:
                instruction_hits.append(chunk)
    if instruction_hits:
        summary = (
            summary
            + "\n\nInstruction/task-description summary:\n"
            + "\n\n---\n\n".join(instruction_hits[:3])
        ).strip()
    return summary


def extract_code_quality(text: str, max_lines: int = 120) -> str:
    lines = normalize_lines(text)
    upper_text = text.upper()
    result_lines = [
        line for line in lines
        if ".value.outcome" not in line and "then \"❌ fail\"" not in line
    ]
    result_text = "\n".join(result_lines)
    result_upper = result_text.upper()
    has_real_failure = (
        "❌" in result_text
        or "STATIC CHECKS FAILED" in result_upper
        or "COMMAND_EXECUTION_ERROR" in result_upper
        or "EXIT STATUS 1" in result_upper
        or "BUILD STATE: FAILED" in result_upper
        or "STATE: FAILED" in result_upper
    )
    if not has_real_failure:
        return ""
    hits: list[int] = []
    patterns = (
        "❌",
        "STATIC CHECKS FAILED",
        "COMMAND_EXECUTION_ERROR",
        "EXIT STATUS",
        "ERROR:",
        "[ERROR]",
        "FAILED WITH",
    )
    for index, line in enumerate(lines):
        upper = line.upper()
        if any(pattern in upper for pattern in patterns):
            hits.append(index)
    if not hits:
        return "\n".join(lines[-40:]).strip()

    ranges: list[tuple[int, int]] = []
    for hit in hits[:8]:
        ranges.append((max(0, hit - 5), min(len(lines), hit + 16)))

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    chunks = ["\n".join(lines[start:end]).strip() for start, end in merged]
    body = "\n\n---\n\n".join(chunk for chunk in chunks if chunk)
    return "\n".join(body.splitlines()[:max_lines]).strip()


def extract_quality_report(text: str, max_lines: int = 90) -> str:
    lines = normalize_lines(text)
    hits: list[int] = []
    for index, line in enumerate(lines):
        lower = line.lower()
        if (
            "❌" in line
            or lower.startswith("fail")
            or " fail -" in lower
            or "behavior_in_task_description" in lower
            or "instruction sufficiency" in lower
            or "task instruction" in lower
            or "needs revision" in lower
            or "vulnerable" in lower
            or "weak assertions" in lower
            or lower.startswith("problem:")
            or lower.startswith("required fix:")
        ):
            hits.append(index)
    if not hits:
        return ""

    ranges: list[tuple[int, int]] = []
    for hit in hits[:8]:
        ranges.append((max(0, hit - 2), min(len(lines), hit + 10)))

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    chunks = ["\n".join(lines[start:end]).strip() for start, end in merged]
    body = clean_excerpt("\n\n---\n\n".join(chunk for chunk in chunks if chunk))
    return "\n".join(body.splitlines()[:max_lines]).strip()


def extract_actionable_blocks(text: str, max_blocks: int = 6, context: int = 2) -> str:
    lines = normalize_lines(text)
    if not lines:
        return ""

    hits: list[int] = []
    for index, line in enumerate(lines):
        upper = line.upper()
        if any(pattern in upper for pattern in ACTION_PATTERNS):
            hits.append(index)

    if not hits:
        return "\n".join(lines[:80]).strip()

    ranges: list[tuple[int, int]] = []
    for hit in hits[:max_blocks]:
        start = max(0, hit - context)
        end = min(len(lines), hit + 12)
        ranges.append((start, end))

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 2:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    chunks = []
    for start, end in merged:
        chunk = "\n".join(lines[start:end]).strip()
        if chunk:
            chunks.append(chunk)
    body = "\n\n---\n\n".join(chunks).strip()
    if len(body) > MAX_SECTION_CHARS:
        body = body[:MAX_SECTION_CHARS].rstrip() + "\n...[section truncated by summarizer]"
    return body


def collect_file_mentions(text: str) -> list[str]:
    mentions = set()
    for match in re.finditer(r"(?:(?:steps|environment|docs|scripts|config|data|src|tests|solution)/[A-Za-z0-9_./-]+|task\.toml|rubric\.txt|Dockerfile)", text):
        mentions.add(match.group(0).rstrip(".,:)"))
    return sorted(mentions)


def build_brief(task: str, feedback_dir: Path) -> str:
    sections: list[str] = [
        f"# Revision Brief: {task}",
        "",
        "Use this brief as the primary input for revision work. It is generated from the latest curated feedback files.",
        "",
        "## Checklist",
        "- [ ] Read this brief end to end",
        "- [ ] Fix every actionable issue below or mark it N/A with a reason",
        "- [ ] Update instructions/tests/rubrics when feedback asks for contract or coverage changes",
        "- [ ] Run preflight",
        "- [ ] Run oracle",
        "- [ ] Rebuild upload zip with `scripts/zip.sh`",
        f"- [ ] Run `scripts/check_revision_completion.py --task {task}`",
        "",
    ]

    overrides = read_text(feedback_dir / "USER_OVERRIDES.md")
    if overrides:
        sections.extend([
            "## User Overrides",
            "",
            "These instructions supersede conflicting report feedback.",
            "",
            overrides.strip(),
            "",
        ])

    all_text = []
    seen_bodies: set[str] = set()
    for report_name in REPORT_ORDER:
        path = feedback_dir / report_name
        text = read_text(path)
        if not text:
            continue
        all_text.append(text)
        body = full_report_text(text)
        body_key = re.sub(r"\s+", " ", body).strip()[:3000]
        if body_key and body_key in seen_bodies:
            continue
        if body_key:
            seen_bodies.add(body_key)
        if body:
            sections.extend([f"## {report_name}", "", body, ""])

    mentions = collect_file_mentions("\n".join(all_text))
    if mentions:
        sections.extend(["## Mentioned Files", ""])
        sections.extend(f"- `{mention}`" for mention in mentions)
        sections.append("")

    sources = read_text(feedback_dir / "report_sources.txt")
    if sources:
        sections.extend(["## Report Sources", "", sources.strip(), ""])

    return "\n".join(sections).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--feedback-root", default=str(DEFAULT_ROOT))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    feedback_dir = Path(args.feedback_root) / args.task
    if not feedback_dir.exists():
        raise SystemExit(f"Fresh feedback folder not found: {feedback_dir}")

    out_path = Path(args.out) if args.out else feedback_dir / "REVISION_BRIEF.md"
    brief = build_brief(args.task, feedback_dir)
    out_path.write_text(brief, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
