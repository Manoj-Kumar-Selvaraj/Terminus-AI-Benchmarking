#!/usr/bin/env python3
"""Fix common strict-LLMaJ instruction/doc issues on batch 1+2 Go matchers."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scaffold_fresh_batch_20260602 import FRESH_TASKS, write_lf  # noqa: E402
from scaffold_go_tasks_from_bike import TASKS  # noqa: E402

BATCH_SLUGS = [
    "go-escape-room-booking-refund-matcher",
    "go-food-truck-rally-voucher-matcher",
    "go-photo-booth-print-credit-matcher",
    "go-helicopter-tour-deposit-reconciler",
    "go-datacenter-rack-hold-release",
    "go-community-pool-lap-credit-matcher",
    "go-ice-rink-session-credit-matcher",
    "go-laundromat-cycle-rebate-matcher",
    "go-mini-golf-scorecard-credit-matcher",
    "go-museum-visit-audio-credit-matcher",
]

LOAD_TYPOS: dict[str, tuple[str, str]] = {
    "go-food-truck-rally-voucher-matcher": ("loadOrderes", "loadOrders"),
}
for t in FRESH_TASKS:
    if "load_typo" in t:
        LOAD_TYPOS[t["slug"]] = (t["load_typo"], t["load_fix"])


def spec_for(slug: str) -> dict | None:
    for s in TASKS + FRESH_TASKS:
        if s["slug"] == slug:
            return dict(s)
    return None


def normalize_action_file_paths(text: str, action_file: str) -> str:
    """Undo credits.csv substring replacement (print_print_print_credits, etc.)."""
    if not action_file.endswith(".csv"):
        return text
    stem = action_file[: -len(".csv")]
    if stem.endswith("_credits"):
        prefix = stem[: -len("_credits")]
        if prefix:
            bad = re.compile(
                rf"(?:(?:{re.escape(prefix)}_)+){re.escape(prefix)}_credits\.csv"
            )
            text = bad.sub(action_file, text)
            text = re.sub(
                rf"/app/data/(?:(?:{re.escape(prefix)}_)+){re.escape(prefix)}_credits\.csv",
                f"/app/data/{action_file}",
                text,
            )
    if action_file.endswith("_credits.csv"):
        inner = action_file[: -len("_credits.csv")]
        if inner and f"{inner}_{inner}_" in text:
            text = re.sub(
                rf"(?:{re.escape(inner)}_)+{re.escape(inner)}_credits\.csv",
                action_file,
                text,
            )
    return text


def fix_record_layouts(path: Path, spec: dict) -> None:
    if not path.is_file():
        return
    sid, cid, col = spec["source_id"], spec["customer_id"], spec["category_col"]
    text = path.read_text(encoding="utf-8")
    text = text.replace("station_id,", "")
    text = text.replace(",station_id", "")
    text = re.sub(rf",\s*{re.escape(cid)},\s*{re.escape(cid)},", f", {cid},", text)
    text = text.replace("Bills use", f"{spec['entities'].title()} use")
    text = text.replace("Credits use", f"{spec['actions'].title()} use")
    write_lf(path, text)


def patch_operations(path: Path, spec: dict | None, slug: str) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    typo_line = ""
    if slug in LOAD_TYPOS:
        bad, good = LOAD_TYPOS[slug]
        typo_line = (
            f"\nThe starter defines `{bad}`; renaming it to `{good}` is an expected fix.\n"
        )
    if typo_line and bad not in text:
        marker = "The CSV headers and task instructions are authoritative"
        if marker in text:
            text = text.replace(marker, marker + typo_line, 1)
        else:
            text = text.rstrip() + typo_line
    if spec:
        sd, ad = spec["source_date"], spec["action_date"]
        m3 = (
            f"\nMilestone 3 maps CSV `{sd}` / `{ad}` to internal date fields "
            f"(often named RideDate/CreditDate in the starter); CSV column names in "
            f"instructions are authoritative.\n"
        )
        if f"maps CSV `{sd}`" not in text:
            text = text.rstrip() + m3
    write_lf(path, text)


def fix_m3_instruction_text(text: str, spec: dict) -> str:
    sid = spec["source_id"]
    ent = spec["entity"]
    sd = spec["source_date"]
    text = text.replace("full station_id equality", f"full {sid} equality")
    text = text.replace("the trip ", f"the {ent} ")
    text = text.replace("A trip with", f"A {ent} with")
    text = text.replace("unused trip matches", f"unused {ent} matches")
    text = text.replace("eligible trip with", f"eligible {ent} with")
    text = text.replace(f"not later than the trip {sd}", f"not later than the source {sd}")
    text = text.replace("posted trip status", f"posted {ent} status")
    return text


def fix_task(slug: str) -> None:
    dest = ROOT / slug
    if not dest.is_dir():
        print(f"SKIP {slug}")
        return
    spec = spec_for(slug)
    if not spec:
        print(f"SKIP no spec {slug}")
        return

    af = spec["action_file"]
    for path in dest.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        text = normalize_action_file_paths(text, af)
        if path.parent.name == "milestone_3":
            text = fix_m3_instruction_text(text, spec)
        write_lf(path, text)

    fix_record_layouts(dest / "environment/docs/record_layouts.md", spec)
    patch_operations(dest / "environment/docs/operations.md", spec, slug)
    print(f"fixed {slug}")


def main() -> None:
    for slug in BATCH_SLUGS:
        fix_task(slug)


if __name__ == "__main__":
    main()
