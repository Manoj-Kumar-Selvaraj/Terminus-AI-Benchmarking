#!/usr/bin/env python3
"""Scaffold new Go milestone tasks from go-bike-share-trip-credit-matcher."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "go-bike-share-trip-credit-matcher"


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")

TASKS = [
    {
        "slug": "go-arcade-token-credit-matcher",
        "module": "arcade-reconcile",
        "tag": "arcade",
        "title": "arcade token credit",
        "entity": "play",
        "entities": "plays",
        "action": "token credit",
        "actions": "token credits",
        "source_file": "plays.csv",
        "action_file": "token_credits.csv",
        "source_id": "play_id",
        "customer_id": "member_id",
        "category_col": "token_tier",
        "source_date": "play_date",
        "action_date": "credit_date",
        "report": "token_credit_report.csv",
        "summary": "token_credit_summary.json",
        "cats": ("ARC", "PRO", "VIP"),
        "aliases": (("AR", "ARC"), ("PR", "PRO"), ("VI", "VIP")),
        "prefix": "ARC",
    },
    {
        "slug": "go-brewpub-tab-adjustment-matcher",
        "module": "brewpub-reconcile",
        "tag": "brewpub",
        "title": "brewpub tab adjustment",
        "entity": "tab",
        "entities": "tabs",
        "action": "tab adjustment",
        "actions": "tab adjustments",
        "source_file": "tabs.csv",
        "action_file": "adjustments.csv",
        "source_id": "tab_id",
        "customer_id": "patron_id",
        "category_col": "pour_tier",
        "source_date": "tab_date",
        "action_date": "adjust_date",
        "report": "tab_adjustment_report.csv",
        "summary": "tab_adjustment_summary.json",
        "cats": ("PINT", "PITCH", "KEG"),
        "aliases": (("PT", "PINT"), ("PC", "PITCH"), ("KG", "KEG")),
        "prefix": "TAB",
    },
    {
        "slug": "go-carwash-subscription-rebate-matcher",
        "module": "carwash-reconcile",
        "tag": "carwash",
        "title": "carwash subscription rebate",
        "entity": "wash",
        "entities": "washes",
        "action": "rebate",
        "actions": "rebates",
        "source_file": "washes.csv",
        "action_file": "rebates.csv",
        "source_id": "wash_id",
        "customer_id": "customer_id",
        "category_col": "plan_tier",
        "source_date": "wash_date",
        "action_date": "rebate_date",
        "report": "wash_rebate_report.csv",
        "summary": "wash_rebate_summary.json",
        "cats": ("BASIC", "PLUS", "PRO"),
        "aliases": (("BS", "BASIC"), ("PL", "PLUS"), ("PR", "PRO")),
        "prefix": "WSH",
    },
    {
        "slug": "go-escape-room-booking-refund-matcher",
        "module": "escape-reconcile",
        "tag": "escape-room",
        "title": "escape room booking refund",
        "entity": "booking",
        "entities": "bookings",
        "action": "refund",
        "actions": "refunds",
        "source_file": "bookings.csv",
        "action_file": "refunds.csv",
        "source_id": "booking_id",
        "customer_id": "team_id",
        "category_col": "room_tier",
        "source_date": "slot_date",
        "action_date": "refund_date",
        "report": "escape_refund_report.csv",
        "summary": "escape_refund_summary.json",
        "cats": ("EASY", "HARD", "VIP"),
        "aliases": (("EA", "EASY"), ("HD", "HARD"), ("VP", "VIP")),
        "prefix": "ESC",
    },
    {
        "slug": "go-food-truck-rally-voucher-matcher",
        "module": "foodtruck-reconcile",
        "tag": "food-truck",
        "title": "food truck rally voucher",
        "entity": "order",
        "entities": "orders",
        "action": "voucher",
        "actions": "vouchers",
        "source_file": "orders.csv",
        "action_file": "vouchers.csv",
        "source_id": "order_id",
        "customer_id": "vendor_id",
        "category_col": "meal_tier",
        "source_date": "order_date",
        "action_date": "voucher_date",
        "report": "rally_voucher_report.csv",
        "summary": "rally_voucher_summary.json",
        "cats": ("SNACK", "MEAL", "COMBO"),
        "aliases": (("SN", "SNACK"), ("ML", "MEAL"), ("CB", "COMBO")),
        "prefix": "RLY",
    },
    {
        "slug": "go-helicopter-tour-deposit-reconciler",
        "module": "helicopter-reconcile",
        "tag": "helicopter",
        "title": "helicopter tour deposit",
        "entity": "tour",
        "entities": "tours",
        "action": "deposit",
        "actions": "deposits",
        "source_file": "tours.csv",
        "action_file": "deposits.csv",
        "source_id": "tour_id",
        "customer_id": "passenger_id",
        "category_col": "cabin_tier",
        "source_date": "tour_date",
        "action_date": "deposit_date",
        "report": "tour_deposit_report.csv",
        "summary": "tour_deposit_summary.json",
        "cats": ("STD", "PREM", "LUX"),
        "aliases": (("ST", "STD"), ("PM", "PREM"), ("LX", "LUX")),
        "prefix": "HEL",
    },
    {
        "slug": "go-ice-rink-session-credit-matcher",
        "module": "icerink-reconcile",
        "tag": "ice-rink",
        "title": "ice rink session credit",
        "entity": "session",
        "entities": "sessions",
        "action": "session credit",
        "actions": "session credits",
        "source_file": "sessions.csv",
        "action_file": "session_credits.csv",
        "source_id": "session_id",
        "customer_id": "skater_id",
        "category_col": "rink_pass",
        "source_date": "session_date",
        "action_date": "credit_date",
        "report": "rink_credit_report.csv",
        "summary": "rink_credit_summary.json",
        "cats": ("PRAC", "GAME", "LEAG"),
        "aliases": (("PR", "PRAC"), ("GM", "GAME"), ("LG", "LEAG")),
        "prefix": "ICE",
    },
    {
        "slug": "go-photo-booth-print-credit-matcher",
        "module": "photobooth-reconcile",
        "tag": "photo-booth",
        "title": "photo booth print credit",
        "entity": "print job",
        "entities": "print jobs",
        "action": "print credit",
        "actions": "print credits",
        "source_file": "prints.csv",
        "action_file": "print_credits.csv",
        "source_id": "print_id",
        "customer_id": "guest_id",
        "category_col": "pack_tier",
        "source_date": "print_date",
        "action_date": "credit_date",
        "report": "print_credit_report.csv",
        "summary": "print_credit_summary.json",
        "cats": ("MINI", "STANDARD", "MAX"),
        "aliases": (("MI", "MINI"), ("SD", "STANDARD"), ("MX", "MAX")),
        "prefix": "PHT",
    },
    {
        "slug": "go-solar-install-rebate-matcher",
        "module": "solar-reconcile",
        "tag": "solar",
        "title": "solar install rebate",
        "entity": "install",
        "entities": "installs",
        "action": "rebate",
        "actions": "rebates",
        "source_file": "installs.csv",
        "action_file": "rebates.csv",
        "source_id": "install_id",
        "customer_id": "site_id",
        "category_col": "system_tier",
        "source_date": "install_date",
        "action_date": "rebate_date",
        "report": "solar_rebate_report.csv",
        "summary": "solar_rebate_summary.json",
        "cats": ("HOME", "BIZ", "IND"),
        "aliases": (("HO", "HOME"), ("BZ", "BIZ"), ("IN", "IND")),
        "prefix": "SOL",
    },
    {
        "slug": "go-winery-tasting-refund-matcher",
        "module": "winery-reconcile",
        "tag": "winery",
        "title": "winery tasting refund",
        "entity": "tasting",
        "entities": "tastings",
        "action": "tasting refund",
        "actions": "tasting refunds",
        "source_file": "tastings.csv",
        "action_file": "tasting_refunds.csv",
        "source_id": "tasting_id",
        "customer_id": "guest_id",
        "category_col": "flight_tier",
        "source_date": "tasting_date",
        "action_date": "refund_date",
        "report": "winery_refund_report.csv",
        "summary": "winery_refund_summary.json",
        "cats": ("RED", "WHITE", "MIXED"),
        "aliases": (("RD", "RED"), ("WH", "WHITE"), ("MX", "MIXED")),
        "prefix": "WIN",
    },
]


def rubric_for(spec: dict) -> str:
    col = spec["category_col"]
    return f"""# Rubric 1

Agent investigates `/app/cmd/reconcile/main.go`, input CSV layouts, and output contracts for `{spec['slug']}`, +2
Agent compiles the Go CLI with `/usr/local/go/bin/go` and runs it against fresh synthetic inputs, +3
Agent fixes reconciliation logic instead of hardcoding `/app/out/{spec['report']}` or `/app/out/{spec['summary']}`, +3
Agent enforces milestone 1 matching gates for full `{spec['source_id']}`, `{spec['customer_id']}`, amount, `COMPLETED` status, and allowed `{col}` values, +5
Agent preserves action input order, exact report columns, and exact `MATCHED` and `UNMATCHED` labels, +3
Agent leaves `{col}` blank on every `UNMATCHED` row and emits canonical `{col}` on `MATCHED` rows, +3
Agent writes summary JSON with positive integer `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`, +3
Agent consumes each source row at most once so duplicate actions cannot reuse the same row, +5
Agent trims surrounding whitespace from CSV identifiers before comparing or writing report fields, +3
Agent hardcodes final CSV or JSON output instead of repairing the Go program, -5

# Rubric 2

Agent normalizes legacy action aliases to canonical `{col}` values before matching and report output, +5
Agent emits canonical `{col}` values on matched alias rows rather than raw alias codes, +3
Agent preserves milestone 1 blank-unmatched `{col}` behavior while adding alias normalization, +3
Agent keeps required output paths and schemas unchanged when extending alias handling, +3
Agent validates alias and consumption behavior against overwritten fixture data, +2
Agent regresses milestone 1 matching gates while implementing alias normalization, -3
Agent edits verifier harness files or solution scaffolding to force a pass, -5
Agent repeats failing `go build` commands without adjusting approach after clear compile errors, -2

# Rubric 3

Agent applies open action-date gates from `/app/config/cutoff_calendar.txt` while preserving prior matching rules, +5
Agent chooses the eligible source row with the latest `{spec['source_date']}` when multiple unused rows qualify, +5
Agent breaks tied `{spec['source_date']}` values by selecting the earliest source input row and tracks consumption by row position, +3
Agent rejects closed, missing, blank, or unlisted calendar dates and blank source dates, +3
Agent preserves alias normalization and blank unmatched `{col}` under calendar gates, +3
Agent verifies latest-date selection with distinct source amounts so first-fit file order cannot pass, +3
Agent validates final CSV and JSON artifacts before finishing milestone 3, +2
Agent treats closed or unlisted calendar dates as open, -5
Agent regresses milestone 1 or 2 behavior while implementing calendar or latest-date logic, -3
"""


def solve1_sh(spec: dict) -> str:
    c0, c1, c2 = spec["cats"]
    allowed_old = (
        "func allowedPassType(pass_type string) bool {\n"
        f'\treturn pass_type == "{c0}" || pass_type == "{c1}" || pass_type == "{c2}"\n'
        "}"
    )
    allowed_new = (
        "func clean(value string) string {\n"
        "\treturn strings.TrimSpace(value)\n"
        "}\n\n"
        "func allowedPassType(pass_type string) bool {\n"
        "\tpass_type = strings.ToUpper(clean(pass_type))\n"
        f'\treturn pass_type == "{c0}" || pass_type == "{c1}" || pass_type == "{c2}"\n'
        "}"
    )
    return f'''#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "func clean(value string)" in text:
    raise SystemExit(0)
if '"strings"' not in text:
    text = text.replace('"strconv"', '"strconv"\\n\\t"strings"')
text = text.replace('amount, err := strconv.Atoi(row[2])', 'amount, err := strconv.Atoi(clean(row[2]))')
text = text.replace(
    'out = append(out, Trip{{ID: row[0], Customer: row[1], Amount: amount, Status: row[3], PassType: row[4]}})',
    'out = append(out, Trip{{ID: clean(row[0]), Customer: clean(row[1]), Amount: amount, Status: strings.ToUpper(clean(row[3])), PassType: strings.ToUpper(clean(row[4]))}})',
)
text = text.replace(
    'out = append(out, Credit{{TripID: row[0], Customer: row[1], Amount: amount, PassType: row[3]}})',
    'out = append(out, Credit{{TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount, PassType: strings.ToUpper(clean(row[3]))}})',
)
text = text.replace(
    'summary.MatchedAmountCents -= credit.Amount',
    'summary.MatchedAmountCents += credit.Amount',
)
text = text.replace(
    'if len(trip.ID) >= 8 && len(credit.TripID) >= 8 &&\\n\\t\\t\\ttrip.ID[:8] == credit.TripID[:8] &&',
    'if trip.ID == credit.TripID &&',
)
text = text.replace(
    '\\tsummary := Summary{{}}\\n\\tfor _, credit := range credits {{\\n\\t\\tmatch := findMatch(trips, credit)',
    '\\tsummary := Summary{{}}\\n\\tusedRecords := make([]bool, len(trips))\\n\\tfor _, credit := range credits {{\\n\\t\\tmatchIndex := findMatch(trips, credit, usedRecords)\\n\\t\\tvar match *Trip\\n\\t\\tif matchIndex >= 0 {{\\n\\t\\t\\tmatch = &trips[matchIndex]\\n\\t\\t\\tusedRecords[matchIndex] = true\\n\\t\\t}}',
)
text = text.replace(
    'func findMatch(trips []Trip, credit Credit) *Trip {{\\n\\tfor i := range trips {{\\n\\t\\ttrip := &trips[i]\\n\\t\\tif trip.ID == credit.TripID &&',
    'func findMatch(trips []Trip, credit Credit, used []bool) int {{\\n\\tfor i := range trips {{\\n\\t\\tif used[i] {{\\n\\t\\t\\tcontinue\\n\\t\\t}}\\n\\t\\ttrip := &trips[i]\\n\\t\\tif trip.ID == credit.TripID &&',
)
text = text.replace(
    '\\t\\t\\treturn trip\\n\\t\\t}}\\n\\t}}\\n\\treturn nil\\n}}',
    '\\t\\t\\treturn i\\n\\t\\t}}\\n\\t}}\\n\\treturn -1\\n}}',
)
text = text.replace(
    {allowed_old!r},
    {allowed_new!r},
)
text = text.replace(
    'return os.WriteFile("/app/out/credit_summary.json"',
    'return os.WriteFile("/app/out/{spec["summary"]}"',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/{spec['report']}
test -s /app/out/{spec['summary']}
'''


def solve2_sh(spec: dict) -> str:
    alias_cases = "\n".join(
        f'\tcase "{a}":\n\t\treturn "{c}"' for a, c in spec["aliases"]
    )
    c0, c1, c2 = spec["cats"]
    canon_old = (
        "func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\n"
        "func allowedPassType(pass_type string) bool {\n\tpass_type = strings.ToUpper(clean(pass_type))\n"
        f'\treturn pass_type == "{c0}" || pass_type == "{c1}" || pass_type == "{c2}"\n'
        "}"
    )
    canon_new = (
        "func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\n"
        "func canonicalPassType(pass_type string) string {\n\tswitch strings.ToUpper(clean(pass_type)) {\n"
        f"{alias_cases}\n"
        "\tdefault:\n\t\treturn strings.ToUpper(clean(pass_type))\n\t}\n}\n\n"
        "func allowedPassType(pass_type string) bool {\n\tpass_type = canonicalPassType(pass_type)\n"
        f'\treturn pass_type == "{c0}" || pass_type == "{c1}" || pass_type == "{c2}"\n'
        "}"
    )
    return f'''#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

if "func canonicalPassType(pass_type string)" in text:
    raise SystemExit(0)

text = text.replace(
    "PassType: strings.ToUpper(clean(row[4]))",
    "PassType: canonicalPassType(row[4])",
)
text = text.replace(
    "PassType: strings.ToUpper(clean(row[3]))",
    "PassType: canonicalPassType(row[3])",
)
text = text.replace(
    {canon_old!r},
    {canon_new!r},
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/{spec['report']}
test -s /app/out/{spec['summary']}
'''


def solve3_sh(spec: dict) -> str:
    text = (TEMPLATE / "steps/milestone_3/solution/solve3.sh").read_text(encoding="utf-8")
    for old, new in (
        ("credit_report.csv", spec["report"]),
        ("credit_summary.json", spec["summary"]),
        ("trips.csv", spec["source_file"]),
        ("credits.csv", spec["action_file"]),
        ("ride_date", spec["source_date"]),
        ("credit_date", spec["action_date"]),
    ):
        text = text.replace(old, new)
    return text


def apply_go_replacements(text: str, spec: dict) -> str:
    c0, c1, c2 = spec["cats"]
    pairs = [
        ("/app/data/trips.csv", f"/app/data/{spec['source_file']}"),
        ("/app/data/credits.csv", f"/app/data/{spec['action_file']}"),
        ('"credit_report.csv"', f'"{spec["report"]}"'),
        ('"credit_summary.json"', f'"{spec["summary"]}"'),
        ("/app/out/credit_summary.json", f"/app/out/{spec['summary']}"),
        (
            '"trip_id", "rider_id", "pass_type", "amount_cents", "status"',
            f'"{spec["source_id"]}", "{spec["customer_id"]}", "{spec["category_col"]}", "amount_cents", "status"',
        ),
        ('return pass_type == "DAY" || pass_type == "MONTH" || pass_type == "ANNUAL"', f'return pass_type == "{c0}" || pass_type == "{c1}" || pass_type == "{c2}"'),
    ]
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def apply_replacements(text: str, spec: dict) -> str:
    protected = []
    for token, placeholder in (
        ("INVOICES", "@@ROW_FIXTURE_A@@"),
        ("PAYMENTS", "@@ROW_FIXTURE_B@@"),
    ):
        if token in text:
            text = text.replace(token, placeholder)
            protected.append((placeholder, token))
    pairs = [
        ("go-bike-share-trip-credit-matcher", spec["slug"]),
        ("bike-share", spec["tag"]),
        ("bike share", spec["title"]),
        ("trip credit", spec["action"]),
        ("trip credits", spec["actions"]),
        ("trips.csv", spec["source_file"]),
        ("credits.csv", spec["action_file"]),
        ("trip_id", spec["source_id"]),
        ("rider_id", spec["customer_id"]),
        ("pass_type", spec["category_col"]),
        ("ride_date", spec["source_date"]),
        ("credit_date", spec["action_date"]),
        ("credit_report.csv", spec["report"]),
        ("credit_summary.json", spec["summary"]),
        ("bill-reconcile", spec["module"]),
        ("BILL", spec["prefix"]),
        ("INV", spec["prefix"]),
        ("DAY", spec["cats"][0]),
        ("MONTH", spec["cats"][1]),
        ("ANNUAL", spec["cats"][2]),
        ("The trip reconciliation", f"The {spec['entity']} reconciliation"),
        ("trip reconciliation", f"{spec['entity']} reconciliation"),
        ("same-day credits", f"same-day {spec['actions']}"),
        ("MONTH credits", f"{spec['cats'][1]} {spec['actions']}"),
        ("trip id", f"{spec['source_id'].replace('_', ' ')}"),
        ("A credit matches", f"A {spec['action']} matches"),
        ("duplicate credits", f"duplicate {spec['actions']}"),
        ("per credit", f"per {spec['action'].split()[-1]}"),
        ("the credit's pass_type", f"the {spec['action']}'s {spec['category_col']}"),
        ("no trip matched", f"no {spec['entity']} matched"),
        ("Each trip can", f"Each {spec['entity']} can"),
        ("the same trip", f"the same {spec['entity']}"),
    ]
    for old, new in pairs:
        text = text.replace(old, new)
    for placeholder, token in protected:
        text = text.replace(placeholder, token)
    return text


def rename_data_files(dest: Path, spec: dict) -> None:
    data = dest / "environment/data"
    trips = data / "trips.csv"
    credits = data / "credits.csv"
    if trips.exists():
        trips.rename(data / spec["source_file"])
    if credits.exists():
        credits.rename(data / spec["action_file"])


def patch_m1_tests(path: Path, spec: dict) -> None:
    c0, c1, c2 = spec["cats"]
    col = spec["category_col"]
    prefix = spec["prefix"]
    text = path.read_text(encoding="utf-8")
    text = text.replace("completed , month ", f"completed , {c0.lower()} ")
    text = text.replace("COMPLETED,annual", f"COMPLETED,{c2.lower()}")
    text = text.replace("completed,annual", f"completed,{c2.lower()}")
    text = text.replace(
        f'"{prefix}6601,CUST6601, 6100 ,{c1}"',
        f'"{prefix}6601,CUST6601, 6100 ,{c0}"',
    )
    text = text.replace(
        f'assert [row["{col}"] for row in rows] == ["{c1}", "{c2}"]',
        f'assert [row["{col}"] for row in rows] == ["{c0}", "{c2}"]',
    )
    path.write_text(text, encoding="utf-8")


def patch_alias_tests(path: Path, spec: dict) -> None:
    a0, a1, a2 = (alias for alias, _ in spec["aliases"])
    text = path.read_text(encoding="utf-8")
    text = text.replace(",MO", f",{a1}")
    text = text.replace(",mo", f",{a1.lower()}")
    text = text.replace(",AN", f",{a2}")
    text = text.replace(",DY", f",{a0}")
    text = text.replace("Legacy DY, MO, and AN", f"Legacy {a0}, {a1}, and {a2}")
    text = text.replace("The DY alias", f"The {a0} alias")
    path.write_text(text, encoding="utf-8")


def patch_m1_instruction(path: Path, spec: dict) -> None:
    col = spec["category_col"]
    text = path.read_text(encoding="utf-8")
    extra = (
        f" The report must keep one row per {spec['action']} in input order. "
        f"Unmatched rows must leave `{col}` blank (empty CSV field). "
        f"Matched rows emit the canonical source `{col}`. "
        f"Trim incidental spaces from identifier fields in report output."
    )
    if "Unmatched rows must leave" not in text:
        text = text.replace(
            "with credit amounts counted as positive cents.",
            "with credit amounts counted as positive cents." + extra,
        )
    path.write_text(text, encoding="utf-8")


def patch_m3_instruction(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    sd, ad = spec["source_date"], spec["action_date"]
    if "earliest trip row" in text:
        text = text.replace("trip row", f"{spec['entity']} row")
        text = text.replace("ride_dates tie", f"{sd} values tie")
        text = text.replace("latest ride_date", f"latest {sd}")
        text = text.replace("ride_date", sd)
        text = text.replace("credit_date", ad)
        text = text.replace("trip input row position", f"{spec['entity']} input row position")
        text = text.replace("trip_id", spec["source_id"])
    path.write_text(text, encoding="utf-8")


def scaffold_task(spec: dict) -> None:
    dest = ROOT / spec["slug"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATE, dest)

    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".pyc":
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path.suffix == ".go":
            content = apply_go_replacements(content, spec)
        else:
            content = apply_replacements(content, spec)
        path.write_text(content, encoding="utf-8")

    write_lf(dest / "steps/milestone_1/solution/solve1.sh", solve1_sh(spec))
    write_lf(dest / "steps/milestone_2/solution/solve2.sh", solve2_sh(spec))
    write_lf(dest / "steps/milestone_3/solution/solve3.sh", solve3_sh(spec))
    def _copy_if_diff(src: Path, dst: Path) -> None:
        if src.resolve() != dst.resolve():
            shutil.copy(src, dst)

    for milestone, num in (("milestone_1", 1), ("milestone_2", 2), ("milestone_3", 3)):
        mdir = dest / "steps" / milestone / "solution"
        _copy_if_diff(dest / "steps/milestone_1/solution/solve1.sh", mdir / "solve1.sh")
        if num >= 2:
            _copy_if_diff(dest / "steps/milestone_2/solution/solve2.sh", mdir / "solve2.sh")
        if num >= 3:
            _copy_if_diff(dest / "steps/milestone_3/solution/solve3.sh", mdir / "solve3.sh")
        wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
bash "$SCRIPT_DIR/solve{num}.sh"
"""
        write_lf(mdir / "solve.sh", wrapper)

    rename_data_files(dest, spec)
    for sh in dest.rglob("*.sh"):
        write_lf(sh, sh.read_text(encoding="utf-8"))
    patch_m1_tests(dest / "steps/milestone_1/tests/test_m1.py", spec)
    patch_m1_tests(dest / "steps/milestone_2/tests/test_m2.py", spec)
    patch_alias_tests(dest / "steps/milestone_2/tests/test_m2.py", spec)
    patch_alias_tests(dest / "steps/milestone_3/tests/test_m3.py", spec)
    patch_m1_instruction(dest / "steps/milestone_1/instruction.md", spec)
    patch_m3_instruction(dest / "steps/milestone_3/instruction.md", spec)
    (dest / "rubric.txt").write_text(rubric_for(spec), encoding="utf-8")

    toml = dest / "task.toml"
    t = toml.read_text(encoding="utf-8")
    t = re.sub(r'tags = \[.*?\]', f'tags = ["go", "csv", "reconciliation", "{spec["tag"]}", "cli"]', t)
    toml.write_text(t, encoding="utf-8")

    print(f"created {spec['slug']}")


def main() -> None:
    for spec in TASKS:
        scaffold_task(spec)


if __name__ == "__main__":
    main()
