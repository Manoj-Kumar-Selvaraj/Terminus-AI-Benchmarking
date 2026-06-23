#!/usr/bin/env python3
"""Clone go-utility-refund-reconciler into a new domain-specific matcher task."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "go-utility-refund-reconciler"
GO_BASE_IMAGE = (
    "FROM "
    "golang:1.22.12-bookworm@sha256:3d699e4d15d0f8f13c9195c0632a16702b8cbdece2955af1c23b37ae5d55a253"
)


def title(s: str) -> str:
    parts = s.replace("-", "_").split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def build_replacements(cfg: dict) -> list[tuple[str, str]]:
    bill_s = cfg["bill_singular"]
    bill_p = cfg["bill_plural"]
    ref_s = cfg["refund_singular"]
    ref_p = cfg["refund_plural"]
    bill_cap = title(bill_s)
    ref_cap = title(ref_s)
    ch = cfg["channels"]
    aliases: dict[str, str] = cfg["aliases"]

    load_bills = "load" + bill_p[:1].upper() + bill_p[1:]
    load_refunds = "load" + ref_p[:1].upper() + ref_p[1:]
    due_field = title(cfg["due_date_col"])
    ref_date_field = title(cfg["refund_date_col"])
    dim_cap = title(cfg["dim_col"])

    pairs: list[tuple[str, str]] = [
        ("go-utility-refund-reconciler", cfg["task_name"]),
        ("refund_summary.json", cfg["summary_file"]),
        ("refund_report.csv", cfg["report_file"]),
        ("refunds.csv", cfg["refund_file"]),
        ("bills.csv", cfg["bill_file"]),
        ("bill_id", cfg["bill_id_col"]),
        ("customer_id", cfg["customer_col"]),
        ("BillID", f"{bill_cap}ID"),
        ("type Bill struct", f"type {bill_cap} struct"),
        ("type Refund struct", f"type {ref_cap} struct"),
        ("[]Bill", f"[]{bill_cap}"),
        ("[]Refund", f"[]{ref_cap}"),
        ("loadBills", load_bills),
        ("loadRefunds", load_refunds),
        ("usedBills", f"used{bill_cap}s"),
        ("findMatch(bills", f"findMatch({bill_p}"),
        ("writeOutputs(bills", f"writeOutputs({bill_p}"),
        ("bills,", f"{bill_p},"),
        ("refunds,", f"{ref_p},"),
        ("(bills ", f"({bill_p} "),
        ("(refunds ", f"({ref_p} "),
        ("bills []", f"{bill_p} []"),
        ("refunds []", f"{ref_p} []"),
        ("bills)", f"{bill_p})"),
        ("refunds)", f"{ref_p})"),
        ("bills ", f"{bill_p} "),
        ("refunds ", f"{ref_p} "),
        (" for _, refund", f" for _, {ref_s}"),
        ("refund.", f"{ref_s}."),
        ("refund,", f"{ref_s},"),
        ("refund ", f"{ref_s} "),
        ("refund)", f"{ref_s})"),
        ("bill.", f"{bill_s}."),
        ("bill ", f"{bill_s} "),
        ("bill,", f"{bill_s},"),
        ("*Bill", f"*{bill_cap}"),
        ("Bill,", f"{bill_cap},"),
        ("Bill ", f"{bill_cap} "),
        ("Bill{", f"{bill_cap}{{"),
        ("Bill]", f"{bill_cap}]"),
        ("POSTED", cfg["posted_status"]),
        ("due_date", cfg["due_date_col"]),
        ("refund_date", cfg["refund_date_col"]),
        ("DueDate", due_field),
        ("RefundDate", ref_date_field),
        ("bill refund", f"{bill_s} {ref_s}"),
        ("Bill refund", f"{bill_cap} {ref_s}"),
        ("utility refund", f"{cfg['tag_domain']} {ref_s}"),
        ("reconciliation, utility", f"reconciliation, {cfg['tag_domain']}"),
        ('"ACH", "CARD", and "WIRE"', f'"{ch[0]}", "{ch[1]}", and "{ch[2]}"'),
        ("(`ACH`, `CARD`, or `WIRE`)", f"(`{ch[0]}`, `{ch[1]}`, or `{ch[2]}`)"),
        ("canonical `ACH`, `CARD`, or `WIRE`", f"canonical `{ch[0]}`, `{ch[1]}`, or `{ch[2]}`"),
        ('channel == "ACH" || channel == "CARD" || channel == "WIRE"', f'channel == "{ch[0]}" || channel == "{ch[1]}" || channel == "{ch[2]}"'),
        ('return channel == "ACH" || channel == "CARD" || channel == "WIRE"', f'return channel == "{ch[0]}" || channel == "{ch[1]}" || channel == "{ch[2]}"'),
        ("bill_id,customer_id,channel", f"{cfg['bill_id_col']},{cfg['customer_col']},{cfg['dim_col']}"),
        ("bill_id,customer_id,amount_cents,status,channel", f"{cfg['bill_id_col']},{cfg['customer_col']},amount_cents,status,{cfg['dim_col']}"),
        ("bill_id,customer_id,amount_cents,channel", f"{cfg['bill_id_col']},{cfg['customer_col']},amount_cents,{cfg['dim_col']}"),
        ("The bill reconciliation CLI", f"The {bill_s} reconciliation CLI"),
        ("same-day refunds", f"same-day {ref_p}"),
        ("Card refunds", f"{ch[1]} {ref_p}"),
        ("bill id collision", f"{bill_s} id collision"),
        ("A refund matches", f"A {ref_s} matches"),
        ("posted bill status", f"posted {bill_s} status"),
        ("Each bill can", f"Each {bill_s} can"),
        ("duplicate refunds", f"duplicate {ref_p}"),
        ("one row per refund", f"one row per {ref_s}"),
        ("refund's channel", f"{ref_s}'s {cfg['dim_col']}"),
        ("no bill matched", f"no {bill_s} matched"),
        ("refund amounts", f"{ref_s} amounts"),
        ("legacy refund export", f"legacy {ref_s} export"),
        ("channel aliases", f"{cfg['dim_col']} aliases"),
        ("refund channel aliases", f"{ref_s} {cfg['dim_col']} aliases"),
        ("refund input order", f"{ref_s} input order"),
        ("dated refund batches", f"dated {ref_s} batches"),
        ("refund date", cfg["refund_date_col"].replace("_", " ")),
        ("bill due date", f"{bill_s} {cfg['due_date_col'].replace('_', ' ')}"),
        ("missing due date", f"missing {cfg['due_date_col'].replace('_', ' ')}"),
        ("latest due date", f"latest {cfg['due_date_col'].replace('_', ' ')}"),
        ("due dates tie", f"{cfg['due_date_col'].replace('_', ' ')}s tie"),
        ("earliest bill row", f"earliest {bill_s} row"),
    ]
    # channel column rename in struct (last to avoid partials)
    pairs.extend([
        ("Channel", dim_cap),
        ("channel", cfg["dim_col"]),
    ])
    for old_alias, new_canon in aliases.items():
        pairs.append((f'case "{old_alias}"', f'case "{old_alias}"'))  # keep keys in solve; patch below
    return sorted(pairs, key=lambda x: len(x[0]), reverse=True)


def apply_replacements(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def patch_solve2(path: Path, channels: list[str], aliases: dict[str, str], dim_col: str) -> None:
    text = path.read_text()
    cases = "\n".join(f'\tcase "{k}":\n\t\treturn "{v}"' for k, v in aliases.items())
    dim_cap = title(dim_col)
    canon = f'''func canonical{dim_cap}({dim_col} string) string {{
\tswitch strings.ToUpper(clean({dim_col})) {{
{cases}
\tdefault:
\t\treturn strings.ToUpper(clean({dim_col}))
\t}}
}}'''
    text = re.sub(
        rf"func canonical{dim_cap}\({dim_col} string\) string \{{.*?\n\}}",
        canon,
        text,
        count=1,
        flags=re.S,
    )
    allowed = f'return {dim_col} == "{channels[0]}" || {dim_col} == "{channels[1]}" || {dim_col} == "{channels[2]}"'
    text = re.sub(
        rf"return {dim_col} == \"[^\"]+\"( \|\| {dim_col} == \"[^\"]+\"){{2}}",
        allowed,
        text,
    )
    path.write_text(text)


def adapt_solve_script(src: str, cfg: dict) -> str:
    bill_cap = title(cfg["bill_singular"])
    ref_cap = title(cfg["refund_singular"])
    bill_p = cfg["bill_plural"]
    ch = cfg["channels"]
    pairs = [
        ("Bill", bill_cap),
        ("Refund", ref_cap),
        ("bills", bill_p),
        ("bill", cfg["bill_singular"]),
        ("refund", cfg["refund_singular"]),
        ("refunds", cfg["refund_plural"]),
        ("bills.csv", cfg["bill_file"]),
        ("refunds.csv", cfg["refund_file"]),
        ("refund_report.csv", cfg["report_file"]),
        ("refund_summary.json", cfg["summary_file"]),
        ("BillID", f"{bill_cap}ID"),
        ("POSTED", cfg["posted_status"]),
        ("DueDate", title(cfg["due_date_col"])),
        ("RefundDate", title(cfg["refund_date_col"])),
        ("due_date", cfg["due_date_col"]),
        ("refund_date", cfg["refund_date_col"]),
        ("Channel", title(cfg["dim_col"])),
        ("channel", cfg["dim_col"]),
        ('return channel == "ACH" || channel == "CARD" || channel == "WIRE"', f'return channel == "{ch[0]}" || channel == "{ch[1]}" || channel == "{ch[2]}"'),
        ('"ACH" || channel == "CARD" || channel == "WIRE"', f'"{ch[0]}" || channel == "{ch[1]}" || channel == "{ch[2]}"'),
    ]
    for old, new in sorted(pairs, key=lambda x: len(x[0]), reverse=True):
        src = src.replace(old, new)
    dim = cfg["dim_col"]
    allowed = f'return {dim} == "{ch[0]}" || {dim} == "{ch[1]}" || {dim} == "{ch[2]}"'
    src = re.sub(
        rf'return {re.escape(dim)} == "ACH" \|\| {re.escape(dim)} == "WIRE"',
        allowed,
        src,
    )
    src = re.sub(
        rf'return {re.escape(dim)} == "ACH" \|\| {re.escape(dim)} == "CARD" \|\| {re.escape(dim)} == "WIRE"',
        allowed,
        src,
    )
    return src


def chain_header(milestone: int) -> str:
    if milestone == 1:
        return ""
    prev = milestone - 1
    return (
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"\n'
        f'bash "$STEPS_DIR/milestone_{prev}/solution/solve{prev}.sh"\n'
    )


def fix_solve_scripts(dest: Path, cfg: dict) -> None:
    template = TEMPLATE
    mapping = {
        1: "solve1.sh",
        2: "solve2.sh",
        3: "solve3.sh",
    }
    for step, name in mapping.items():
        tpl = template / f"steps/milestone_{step}/solution/{name}"
        dst = dest / f"steps/milestone_{step}/solution/{name}"
        body = adapt_solve_script(tpl.read_text(encoding="utf-8"), cfg)
        if step > 1:
            body = body.replace("#!/usr/bin/env bash\nset -euo pipefail\n\ncd /app\n", "")
            body = (
                "#!/usr/bin/env bash\nset -euo pipefail\n\n"
                + chain_header(step)
                + "\ncd /app\n"
                + body.split("cd /app\n", 1)[-1]
            )
        dst.write_text(body, encoding="utf-8")
    patch_solve2(
        dest / "steps/milestone_2/solution/solve2.sh",
        cfg["channels"],
        cfg["aliases"],
        cfg["dim_col"],
    )
    patch_solve3(dest / "steps/milestone_3/solution/solve3.sh", cfg["posted_status"])


def fix_main_go(path: Path, cfg: dict) -> None:
    bill_cap = title(cfg["bill_singular"])
    ref_cap = title(cfg["refund_singular"])
    bill_p = cfg["bill_plural"]
    ref_s = cfg["refund_singular"]
    bill_s = cfg["bill_singular"]
    ch = cfg["channels"]
    text = path.read_text(encoding="utf-8")
    text = text.replace("Refund{", f"{ref_cap}{{")
    text = text.replace(f"{ref_s} Refund", f"{ref_s} {ref_cap}")
    text = text.replace("bills[i]", f"{bill_p}[i]")
    text = text.replace("return bill\n", f"return {bill_s}\n")
    text = text.replace("allowedTerm", f"allowed{title(cfg['dim_col'])}")
    text = text.replace("allowedChannel", f"allowed{title(cfg['dim_col'])}")
    allowed = f'return term == "{ch[0]}" || term == "{ch[1]}" || term == "{ch[2]}"'
    text = re.sub(
        r'return term == "[^"]+"( \|\| term == "[^"]+")*',
        allowed.replace("term", cfg["dim_col"]),
        text,
    )
    dim = cfg["dim_col"]
    text = re.sub(
        rf"return {dim} == \"[^\"]+\"( \|\| {dim} == \"[^\"]+\")*",
        f'return {dim} == "{ch[0]}" || {dim} == "{ch[1]}" || {dim} == "{ch[2]}"',
        text,
    )
    path.write_text(text, encoding="utf-8")


def _alias_for_channel(aliases: dict[str, str], channel: str) -> str:
    for key, value in aliases.items():
        if value == channel:
            return key
    raise KeyError(f"no alias maps to {channel}")


def fix_environment_data(dest: Path, cfg: dict) -> None:
    """Replace template ACH/CARD/WIRE sample values with domain channels."""
    ch = cfg["channels"]
    mid_alias = _alias_for_channel(cfg["aliases"], ch[1])
    legacy = {
        "ACH": ch[0],
        "CARD": ch[1],
        "WIRE": ch[2],
        "CC": mid_alias,
    }
    for path in (dest / "environment").rglob("*.csv"):
        text = path.read_text(encoding="utf-8")
        for old, new in sorted(legacy.items(), key=lambda x: len(x[0]), reverse=True):
            text = text.replace(f",{old}\n", f",{new}\n")
            text = text.replace(f",{old.lower()}\n", f",{new.lower()}\n")
        path.write_text(text, encoding="utf-8")


def fix_test_files(dest: Path, cfg: dict) -> None:
    ch = cfg["channels"]
    aliases = cfg["aliases"]
    mid_alias = _alias_for_channel(aliases, ch[1])
    last_alias = _alias_for_channel(aliases, ch[2])
    legacy = {
        "ACH": ch[0],
        "CARD": ch[1],
        "WIRE": ch[2],
        "CC": mid_alias,
        "WIR": last_alias,
    }
    legacy.update(
        {
            "ach": ch[0].lower(),
            "card": ch[1].lower(),
            "wire": ch[2].lower(),
            "cc": mid_alias.lower(),
            "wir": last_alias.lower(),
            "posted": cfg["posted_status"].lower(),
        }
    )
    for test_path in dest.rglob("test_m*.py"):
        text = test_path.read_text(encoding="utf-8")
        for old, new in sorted(legacy.items(), key=lambda x: len(x[0]), reverse=True):
            text = text.replace(old, new)
        text = text.replace("test_card_refund", f"test_{ch[1].lower()}_{cfg['refund_singular']}")
        text = text.replace("card refund", f"{ch[1].lower()} {cfg['refund_singular']}")
        text = text.replace("Card refunds", f"{ch[1]} {cfg['refund_plural']}")
        text = text.replace("CARD ", f"{ch[1]} ")
        # Legacy alias test: first alias row must use the middle-channel alias (utility CC -> CARD).
        first_alias = list(aliases.keys())[0]
        text = text.replace(f",{first_alias.lower()}\n", f",{mid_alias.lower()}\n", 1)
        text = text.replace(
            f"Legacy {first_alias} and {last_alias}",
            f"Legacy {mid_alias} and {last_alias}",
        )
        test_path.write_text(text, encoding="utf-8")


def write_milestone_instructions(dest: Path, cfg: dict) -> None:
    bill_s = cfg["bill_singular"]
    ref_s = cfg["refund_singular"]
    ref_p = cfg["refund_plural"]
    ch = cfg["channels"]
    aliases = cfg["aliases"]
    alias_text = ", ".join(f"`{k}` means `{v}`" for k, v in aliases.items())
    m1 = f"""The {bill_s} reconciliation CLI in `/app/cmd/reconcile/main.go` is misclassifying a few same-day {ref_p}. {ch[1]} {ref_p} are being left unmatched, one {bill_s} id collision is matching the wrong row, and the matched total is coming out with the wrong sign.

Fix the Go program so it reads `/app/data/{cfg["bill_file"]}` and `/app/data/{cfg["refund_file"]}`, then writes `/app/out/{cfg["report_file"]}` and `/app/out/{cfg["summary_file"]}`. A {ref_s} matches only when {cfg["bill_id_col"]}, {cfg["customer_col"]}, amount, posted {bill_s} status, and an allowed {cfg["dim_col"]} all line up. {cfg["dim_col"].title()}s `{ch[0]}`, `{ch[1]}`, and `{ch[2]}` are allowed. Each {bill_s} can be matched at most once; if duplicate {ref_p} point at the same {bill_s}, only the earliest eligible {ref_s} consumes it. Input fields can have incidental surrounding spaces, and {cfg["dim_col"]} and status comparisons should be case-insensitive.

The report must keep one row per {ref_s} in input order with columns `{cfg["bill_id_col"]},{cfg["customer_col"]},{cfg["dim_col"]},amount_cents,status`; use `MATCHED` or `UNMATCHED` for status, use the {ref_s}'s {cfg["dim_col"]} when matched, and leave `{cfg["dim_col"]}` blank when no {bill_s} matched. Report fields should not carry incidental surrounding spaces from the input. The summary JSON must contain integer fields `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with {ref_s} amounts counted as positive cents.
"""
    m2 = f"""Update the {bill_s} reconciliation CLI in `/app` for a legacy {ref_s} export that uses {cfg["dim_col"]} aliases. The program must still read `/app/data/{cfg["bill_file"]}` and `/app/data/{cfg["refund_file"]}`, then write `/app/out/{cfg["report_file"]}` and `/app/out/{cfg["summary_file"]}`. A {ref_s} matches only when {cfg["bill_id_col"]}, {cfg["customer_col"]}, amount, posted {bill_s} status, and allowed {cfg["dim_col"]} line up; {cfg["bill_id_col"]}s must be compared as full identifiers, fields may have surrounding spaces, and {cfg["dim_col"]} and status comparisons should be case-insensitive. {cfg["dim_col"].title()}s `{ch[0]}`, `{ch[1]}`, and `{ch[2]}` are allowed, and legacy {ref_s} {cfg["dim_col"]} aliases {", ".join(f"`{k}`" for k in aliases)} should be treated as canonical `{ch[0]}`, `{ch[1]}`, and `{ch[2]}`.

Each {bill_s} can be consumed by at most one {ref_s}, with the earliest eligible {ref_s} winning. The report must keep {ref_s} input order with columns `{cfg["bill_id_col"]},{cfg["customer_col"]},{cfg["dim_col"]},amount_cents,status`; matched rows should emit the canonical {cfg["dim_col"]} (`{ch[0]}`, `{ch[1]}`, or `{ch[2]}`), while unmatched rows must leave `{cfg["dim_col"]}` blank. The summary JSON must contain integer fields `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, with {ref_s} amounts counted as positive cents.
"""
    m3 = f"""Extend the {bill_s} reconciliation CLI in `/app/cmd/reconcile/main.go` to handle dated {ref_s} batches. It must still read `/app/data/{cfg["bill_file"]}` and `/app/data/{cfg["refund_file"]}`, then write `/app/out/{cfg["report_file"]}` and `/app/out/{cfg["summary_file"]}` with the same schema and status values from the earlier milestones.

For this milestone, the verifier may add a `{cfg["due_date_col"]}` column to `{cfg["bill_file"]}` and a `{cfg["refund_date_col"]}` column to `{cfg["refund_file"]}`. A {ref_s} can match only when all prior criteria still pass, the {cfg["refund_date_col"]} is listed as `open` in `/app/config/cutoff_calendar.txt`, and the {cfg["refund_date_col"]} is not later than the {bill_s} {cfg["due_date_col"]}. A missing or closed {cfg["refund_date_col"]} is not eligible. A {bill_s} with a missing {cfg["due_date_col"]} is also not eligible because the date comparison cannot be satisfied. If more than one unused {bill_s} matches the same {ref_s}, choose the eligible {bill_s} with the latest {cfg["due_date_col"]}; if {cfg["due_date_col"]}s tie, choose the earliest {bill_s} row. Consumption is tracked by {bill_s} input row position, not by {cfg["bill_id_col"]}, so duplicate ids in separate rows remain independently consumable until their specific rows are used.

Legacy aliases from milestone 2 still apply ({alias_text}), and matched report rows must emit the canonical {cfg["dim_col"]}. Unmatched rows must leave `{cfg["dim_col"]}` blank. Summary amounts remain positive integer cents.
"""
    (dest / "steps/milestone_1/instruction.md").write_text(m1, encoding="utf-8")
    (dest / "steps/milestone_2/instruction.md").write_text(m2, encoding="utf-8")
    (dest / "steps/milestone_3/instruction.md").write_text(m3, encoding="utf-8")


def patch_solve3(path: Path, posted: str) -> None:
    text = path.read_text()
    text = text.replace('Status != "POSTED"', f'Status != "{posted}"')
    text = text.replace("\tTerm   string", "\tTerm  string")
    text = text.replace("\tTerm    string", "\tTerm  string")
    path.write_text(text)


def create_task(cfg: dict) -> None:
    dest = ROOT / cfg["task_name"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATE, dest)
    pairs = build_replacements(cfg)
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".pyc"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        path.write_text(apply_replacements(content, pairs), encoding="utf-8")

    fix_solve_scripts(dest, cfg)
    fix_main_go(dest / "environment/cmd/reconcile/main.go", cfg)
    write_milestone_instructions(dest, cfg)
    fix_test_files(dest, cfg)
    fix_environment_data(dest, cfg)

    bill_path = dest / "environment/data" / cfg["bill_file"]
    refund_path = dest / "environment/data" / cfg["refund_file"]
    old_bill = dest / "environment/data" / "bills.csv"
    old_refund = dest / "environment/data" / "refunds.csv"
    if old_bill.exists() and not bill_path.exists():
        shutil.copy(old_bill, bill_path)
    if old_refund.exists() and not refund_path.exists():
        shutil.copy(old_refund, refund_path)
    for stale in ("bills.csv", "refunds.csv"):
        p = dest / "environment/data" / stale
        if p.exists() and p.name != cfg["bill_file"] and p.name != cfg["refund_file"]:
            p.unlink()
    # Fix CSV headers in seed data
    for path, header in (
        (bill_path, f"{cfg['bill_id_col']},{cfg['customer_col']},amount_cents,status,{cfg['dim_col']}"),
        (refund_path, f"{cfg['bill_id_col']},{cfg['customer_col']},amount_cents,{cfg['dim_col']}"),
    ):
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if lines:
                lines[0] = header
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for sh_path in dest.rglob("*.sh"):
        raw = sh_path.read_bytes()
        sh_path.write_bytes(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))

    dockerfile = dest / "environment/Dockerfile"
    if dockerfile.exists():
        lines = dockerfile.read_text(encoding="utf-8").splitlines()
        if lines:
            lines[0] = GO_BASE_IMAGE
            dockerfile.write_text("\n".join(lines) + "\n", encoding="utf-8")

    toml_path = dest / "task.toml"
    if toml_path.exists():
        toml = toml_path.read_text(encoding="utf-8").replace('"utility"', f'"{cfg["tag_domain"]}"')
        toml_path.write_text(toml, encoding="utf-8")

    print(f"Created {cfg['task_name']}")


TASKS = [
    {
        "task_name": "go-tuition-credit-matcher",
        "bill_singular": "enrollment",
        "bill_plural": "enrollments",
        "refund_singular": "credit",
        "refund_plural": "credits",
        "bill_id_col": "enrollment_id",
        "customer_col": "student_id",
        "dim_col": "term",
        "bill_file": "enrollments.csv",
        "refund_file": "credits.csv",
        "report_file": "credit_report.csv",
        "summary_file": "credit_summary.json",
        "posted_status": "ENROLLED",
        "channels": ["ONL", "MAIL", "CAMP"],
        "aliases": {"WEB": "ONL", "PST": "MAIL", "OFF": "CAMP"},
        "due_date_col": "session_end",
        "refund_date_col": "credit_date",
        "tag_domain": "tuition",
    },
    {
        "task_name": "go-marketplace-payout-matcher",
        "bill_singular": "order",
        "bill_plural": "orders",
        "refund_singular": "payout",
        "refund_plural": "payouts",
        "bill_id_col": "order_id",
        "customer_col": "seller_id",
        "dim_col": "lane",
        "bill_file": "orders.csv",
        "refund_file": "payouts.csv",
        "report_file": "payout_report.csv",
        "summary_file": "payout_summary.json",
        "posted_status": "SHIPPED",
        "channels": ["D2D", "LOCKER", "STORE"],
        "aliases": {"DRP": "D2D", "PKU": "LOCKER", "RTL": "STORE"},
        "due_date_col": "ship_date",
        "refund_date_col": "payout_date",
        "tag_domain": "marketplace",
    },
    {
        "task_name": "go-payroll-advance-matcher",
        "bill_singular": "advance",
        "bill_plural": "advances",
        "refund_singular": "repayment",
        "refund_plural": "repayments",
        "bill_id_col": "advance_id",
        "customer_col": "employee_id",
        "dim_col": "method",
        "bill_file": "advances.csv",
        "refund_file": "repayments.csv",
        "report_file": "repayment_report.csv",
        "summary_file": "repayment_summary.json",
        "posted_status": "ACTIVE",
        "channels": ["DIRECT", "PAYROLL", "DEBIT"],
        "aliases": {"ACH": "DIRECT", "PR": "PAYROLL", "DBT": "DEBIT"},
        "due_date_col": "advance_date",
        "refund_date_col": "repayment_date",
        "tag_domain": "payroll",
    },
    {
        "task_name": "go-event-ticket-refund-matcher",
        "bill_singular": "booking",
        "bill_plural": "bookings",
        "refund_singular": "refund",
        "refund_plural": "refunds",
        "bill_id_col": "booking_id",
        "customer_col": "attendee_id",
        "dim_col": "tier",
        "bill_file": "bookings.csv",
        "refund_file": "refunds.csv",
        "report_file": "refund_report.csv",
        "summary_file": "refund_summary.json",
        "posted_status": "CONFIRMED",
        "channels": ["GA", "VIP", "COMP"],
        "aliases": {"STD": "GA", "PLT": "VIP", "INV": "COMP"},
        "due_date_col": "event_date",
        "refund_date_col": "refund_date",
        "tag_domain": "events",
    },
    {
        "task_name": "go-parking-citation-credit-matcher",
        "bill_singular": "citation",
        "bill_plural": "citations",
        "refund_singular": "credit",
        "refund_plural": "credits",
        "bill_id_col": "citation_id",
        "customer_col": "plate_id",
        "dim_col": "zone",
        "bill_file": "citations.csv",
        "refund_file": "credits.csv",
        "report_file": "credit_report.csv",
        "summary_file": "credit_summary.json",
        "posted_status": "PAID",
        "channels": ["STREET", "GARAGE", "LOT"],
        "aliases": {"ST": "STREET", "GRG": "GARAGE", "LT": "LOT"},
        "due_date_col": "due_date",
        "refund_date_col": "credit_date",
        "tag_domain": "parking",
    },
    {
        "task_name": "go-catering-order-adjustment-matcher",
        "bill_singular": "order",
        "bill_plural": "orders",
        "refund_singular": "adjustment",
        "refund_plural": "adjustments",
        "bill_id_col": "order_id",
        "customer_col": "venue_id",
        "dim_col": "service",
        "bill_file": "orders.csv",
        "refund_file": "adjustments.csv",
        "report_file": "adjustment_report.csv",
        "summary_file": "adjustment_summary.json",
        "posted_status": "FULFILLED",
        "channels": ["PICKUP", "DELIVERY", "ONSITE"],
        "aliases": {"PU": "PICKUP", "DEL": "DELIVERY", "OS": "ONSITE"},
        "due_date_col": "fulfill_date",
        "refund_date_col": "adjustment_date",
        "tag_domain": "catering",
    },
    {
        "task_name": "go-gym-membership-waiver-matcher",
        "bill_singular": "membership",
        "bill_plural": "memberships",
        "refund_singular": "waiver",
        "refund_plural": "waivers",
        "bill_id_col": "membership_id",
        "customer_col": "member_id",
        "dim_col": "plan",
        "bill_file": "memberships.csv",
        "refund_file": "waivers.csv",
        "report_file": "waiver_report.csv",
        "summary_file": "waiver_summary.json",
        "posted_status": "ACTIVE",
        "channels": ["BASIC", "PLUS", "ELITE"],
        "aliases": {"BAS": "BASIC", "PLU": "PLUS", "ELI": "ELITE"},
        "due_date_col": "renewal_date",
        "refund_date_col": "waiver_date",
        "tag_domain": "fitness",
    },
    {
        "task_name": "go-saas-license-rebate-matcher",
        "bill_singular": "license",
        "bill_plural": "licenses",
        "refund_singular": "rebate",
        "refund_plural": "rebates",
        "bill_id_col": "license_id",
        "customer_col": "tenant_id",
        "dim_col": "tier",
        "bill_file": "licenses.csv",
        "refund_file": "rebates.csv",
        "report_file": "rebate_report.csv",
        "summary_file": "rebate_summary.json",
        "posted_status": "LICENSED",
        "channels": ["STARTER", "BUSINESS", "ENTERPRISE"],
        "aliases": {"STR": "STARTER", "BUS": "BUSINESS", "ENT": "ENTERPRISE"},
        "due_date_col": "license_end",
        "refund_date_col": "rebate_date",
        "tag_domain": "saas",
    },
    {
        "task_name": "go-veterinary-visit-credit-matcher",
        "bill_singular": "visit",
        "bill_plural": "visits",
        "refund_singular": "credit",
        "refund_plural": "credits",
        "bill_id_col": "visit_id",
        "customer_col": "owner_id",
        "dim_col": "clinic",
        "bill_file": "visits.csv",
        "refund_file": "credits.csv",
        "report_file": "credit_report.csv",
        "summary_file": "credit_summary.json",
        "posted_status": "CLOSED",
        "channels": ["MAIN", "MOBILE", "ER"],
        "aliases": {"MN": "MAIN", "VAN": "MOBILE", "URG": "ER"},
        "due_date_col": "service_date",
        "refund_date_col": "credit_date",
        "tag_domain": "veterinary",
    },
    {
        "task_name": "go-museum-membership-refund-matcher",
        "bill_singular": "membership",
        "bill_plural": "memberships",
        "refund_singular": "refund",
        "refund_plural": "refunds",
        "bill_id_col": "membership_id",
        "customer_col": "patron_id",
        "dim_col": "program",
        "bill_file": "memberships.csv",
        "refund_file": "refunds.csv",
        "report_file": "refund_report.csv",
        "summary_file": "refund_summary.json",
        "posted_status": "ACTIVE",
        "channels": ["ADULT", "FAMILY", "PATRON"],
        "aliases": {"ADT": "ADULT", "FAM": "FAMILY", "PTR": "PATRON"},
        "due_date_col": "valid_through",
        "refund_date_col": "refund_date",
        "tag_domain": "museum",
    },
    {
        "task_name": "go-logistics-accessorial-credit-matcher",
        "bill_singular": "charge",
        "bill_plural": "charges",
        "refund_singular": "credit",
        "refund_plural": "credits",
        "bill_id_col": "charge_id",
        "customer_col": "shipper_id",
        "dim_col": "mode",
        "bill_file": "charges.csv",
        "refund_file": "credits.csv",
        "report_file": "credit_report.csv",
        "summary_file": "credit_summary.json",
        "posted_status": "BILLED",
        "channels": ["LTL", "FTL", "RAIL"],
        "aliases": {"LESS": "LTL", "FULL": "FTL", "RR": "RAIL"},
        "due_date_col": "invoice_date",
        "refund_date_col": "credit_date",
        "tag_domain": "logistics",
    },
    {
        "task_name": "go-streaming-subscription-refund-matcher",
        "bill_singular": "subscription",
        "bill_plural": "subscriptions",
        "refund_singular": "refund",
        "refund_plural": "refunds",
        "bill_id_col": "subscription_id",
        "customer_col": "subscriber_id",
        "dim_col": "plan",
        "bill_file": "subscriptions.csv",
        "refund_file": "refunds.csv",
        "report_file": "refund_report.csv",
        "summary_file": "refund_summary.json",
        "posted_status": "ACTIVE",
        "channels": ["BASIC", "FAMILY", "PREMIUM"],
        "aliases": {"BSC": "BASIC", "FAM": "FAMILY", "PRM": "PREMIUM"},
        "due_date_col": "cycle_end",
        "refund_date_col": "refund_date",
        "tag_domain": "streaming",
    },
    {
        "task_name": "go-conference-sponsor-rebate-matcher",
        "bill_singular": "sponsorship",
        "bill_plural": "sponsorships",
        "refund_singular": "rebate",
        "refund_plural": "rebates",
        "bill_id_col": "sponsorship_id",
        "customer_col": "sponsor_id",
        "dim_col": "level",
        "bill_file": "sponsorships.csv",
        "refund_file": "rebates.csv",
        "report_file": "rebate_report.csv",
        "summary_file": "rebate_summary.json",
        "posted_status": "SIGNED",
        "channels": ["BRONZE", "GOLD", "PLATINUM"],
        "aliases": {"BRZ": "BRONZE", "GLD": "GOLD", "PLT": "PLATINUM"},
        "due_date_col": "event_end",
        "refund_date_col": "rebate_date",
        "tag_domain": "conference",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Single task name from TASKS list")
    args = parser.parse_args()
    configs = TASKS if not args.task else [c for c in TASKS if c["task_name"] == args.task]
    if not configs:
        raise SystemExit(f"Unknown task {args.task}")
    for cfg in configs:
        create_task(cfg)


if __name__ == "__main__":
    main()
