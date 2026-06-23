#!/usr/bin/env python3
"""Create ten fresh four-milestone Go policy matcher tasks from the hardened waterpark task."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "go-waterpark-pass-refund-matcher"


TASKS = [
    {
        "slug": "go-yoga-studio-class-credit-reconciler",
        "module": "yoga-class-reconcile",
        "tag": "yoga-studio",
        "title": "yoga studio class credit",
        "source_singular": "class",
        "source_plural": "classes",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "classes.csv",
        "action_file": "credits.csv",
        "source_id": "class_id",
        "customer_id": "member_id",
        "kind": "class_type",
        "source_date": "class_date",
        "action_date": "credit_date",
        "report": "class_credit_report.csv",
        "summary": "class_credit_summary.json",
        "cats": ("FLOW", "POWER", "PRIVATE"),
        "aliases": ("FL", "PW", "PR"),
        "prefix": "YOG",
    },
    {
        "slug": "go-dentist-appointment-copay-credit-matcher",
        "module": "dental-copay-reconcile",
        "tag": "dental",
        "title": "dentist appointment copay credit",
        "source_singular": "appointment",
        "source_plural": "appointments",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "appointments.csv",
        "action_file": "credits.csv",
        "source_id": "appointment_id",
        "customer_id": "patient_id",
        "kind": "service_type",
        "source_date": "appointment_date",
        "action_date": "credit_date",
        "report": "copay_credit_report.csv",
        "summary": "copay_credit_summary.json",
        "cats": ("CLEAN", "XRAY", "SURG"),
        "aliases": ("CL", "XR", "SG"),
        "prefix": "DEN",
    },
    {
        "slug": "go-ferry-ticket-rebooking-credit-matcher",
        "module": "ferry-ticket-reconcile",
        "tag": "ferry",
        "title": "ferry ticket rebooking credit",
        "source_singular": "ticket",
        "source_plural": "tickets",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "tickets.csv",
        "action_file": "credits.csv",
        "source_id": "ticket_id",
        "customer_id": "rider_id",
        "kind": "fare_type",
        "source_date": "travel_date",
        "action_date": "credit_date",
        "report": "ticket_credit_report.csv",
        "summary": "ticket_credit_summary.json",
        "cats": ("ECON", "BIKE", "CABIN"),
        "aliases": ("EC", "BK", "CB"),
        "prefix": "FRY",
    },
    {
        "slug": "go-childcare-attendance-credit-matcher",
        "module": "childcare-attendance-reconcile",
        "tag": "childcare",
        "title": "childcare attendance credit",
        "source_singular": "attendance",
        "source_plural": "attendances",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "attendances.csv",
        "action_file": "credits.csv",
        "source_id": "attendance_id",
        "customer_id": "child_id",
        "kind": "care_type",
        "source_date": "attendance_date",
        "action_date": "credit_date",
        "report": "attendance_credit_report.csv",
        "summary": "attendance_credit_summary.json",
        "cats": ("HALF", "FULL", "EXT"),
        "aliases": ("HF", "FD", "EX"),
        "prefix": "CHD",
    },
    {
        "slug": "go-fitness-pt-session-rebate-matcher",
        "module": "fitness-session-reconcile",
        "tag": "fitness",
        "title": "fitness personal training session rebate",
        "source_singular": "session",
        "source_plural": "sessions",
        "action_singular": "rebate",
        "action_plural": "rebates",
        "source_file": "sessions.csv",
        "action_file": "rebates.csv",
        "source_id": "session_id",
        "customer_id": "client_id",
        "kind": "training_type",
        "source_date": "session_date",
        "action_date": "rebate_date",
        "report": "session_rebate_report.csv",
        "summary": "session_rebate_summary.json",
        "cats": ("SOLO", "DUO", "TEAM"),
        "aliases": ("SO", "DU", "TM"),
        "prefix": "FIT",
    },
    {
        "slug": "go-coffee-roastery-workshop-refund-matcher",
        "module": "coffee-workshop-reconcile",
        "tag": "coffee-roastery",
        "title": "coffee roastery workshop refund",
        "source_singular": "workshop",
        "source_plural": "workshops",
        "action_singular": "refund",
        "action_plural": "refunds",
        "source_file": "workshops.csv",
        "action_file": "refunds.csv",
        "source_id": "workshop_id",
        "customer_id": "attendee_id",
        "kind": "workshop_type",
        "source_date": "workshop_date",
        "action_date": "refund_date",
        "report": "workshop_refund_report.csv",
        "summary": "workshop_refund_summary.json",
        "cats": ("BREW", "ROAST", "CUP"),
        "aliases": ("BW", "RS", "CP"),
        "prefix": "COF",
    },
    {
        "slug": "go-farm-equipment-rental-credit-matcher",
        "module": "farm-rental-reconcile",
        "tag": "farm-equipment",
        "title": "farm equipment rental credit",
        "source_singular": "rental",
        "source_plural": "rentals",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "rentals.csv",
        "action_file": "credits.csv",
        "source_id": "rental_id",
        "customer_id": "account_id",
        "kind": "equipment_type",
        "source_date": "rental_date",
        "action_date": "credit_date",
        "report": "rental_credit_report.csv",
        "summary": "rental_credit_summary.json",
        "cats": ("TRACTOR", "SPRAY", "LIFT"),
        "aliases": ("TR", "SP", "LF"),
        "prefix": "FRM",
    },
    {
        "slug": "go-aquarium-tour-refund-matcher",
        "module": "aquarium-tour-reconcile",
        "tag": "aquarium",
        "title": "aquarium tour refund",
        "source_singular": "tour",
        "source_plural": "tours",
        "action_singular": "refund",
        "action_plural": "refunds",
        "source_file": "tours.csv",
        "action_file": "refunds.csv",
        "source_id": "tour_id",
        "customer_id": "guest_id",
        "kind": "tour_type",
        "source_date": "tour_date",
        "action_date": "refund_date",
        "report": "tour_refund_report.csv",
        "summary": "tour_refund_summary.json",
        "cats": ("REEF", "SHARK", "VIP"),
        "aliases": ("RF", "SH", "VP"),
        "prefix": "AQU",
    },
    {
        "slug": "go-dance-studio-recital-credit-matcher",
        "module": "dance-recital-reconcile",
        "tag": "dance-studio",
        "title": "dance studio recital credit",
        "source_singular": "booking",
        "source_plural": "bookings",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "bookings.csv",
        "action_file": "credits.csv",
        "source_id": "booking_id",
        "customer_id": "dancer_id",
        "kind": "recital_type",
        "source_date": "recital_date",
        "action_date": "credit_date",
        "report": "recital_credit_report.csv",
        "summary": "recital_credit_summary.json",
        "cats": ("SOLO", "GROUP", "STAGE"),
        "aliases": ("SL", "GP", "ST"),
        "prefix": "DAN",
    },
    {
        "slug": "go-cinema-private-screening-credit-matcher",
        "module": "cinema-screening-reconcile",
        "tag": "cinema",
        "title": "cinema private screening credit",
        "source_singular": "screening",
        "source_plural": "screenings",
        "action_singular": "credit",
        "action_plural": "credits",
        "source_file": "screenings.csv",
        "action_file": "credits.csv",
        "source_id": "screening_id",
        "customer_id": "host_id",
        "kind": "screen_type",
        "source_date": "screening_date",
        "action_date": "credit_date",
        "report": "screening_credit_report.csv",
        "summary": "screening_credit_summary.json",
        "cats": ("SMALL", "PREM", "IMAX"),
        "aliases": ("SM", "PM", "IX"),
        "prefix": "CIN",
    },
]


def cap_words(value: str) -> str:
    return "".join(part.capitalize() for part in value.replace("_", "-").split("-"))


def replace_text(text: str, spec: dict) -> str:
    cat1, cat2, cat3 = spec["cats"]
    al1, al2, al3 = spec["aliases"]
    source = spec["source_singular"]
    sources = spec["source_plural"]
    action = spec["action_singular"]
    actions = spec["action_plural"]
    sid = spec["source_id"]
    cid = spec["customer_id"]
    kind = spec["kind"]
    sdate = spec["source_date"]
    adate = spec["action_date"]
    src_cap = cap_words(source)
    act_cap = cap_words(action)
    replacements = [
        ("go-waterpark-pass-refund-matcher", spec["slug"]),
        ("bill-reconcile", spec["module"]),
        ("waterpark", spec["tag"]),
        ("pass refund", f"{source} {action}"),
        ("pass refunds", f"{source} {actions}"),
        ("Pass refund", f"{src_cap} {action}"),
        ("Pass refunds", f"{src_cap} {actions}"),
        ("BILLS", cap_words(sources).upper()),
        ("INVOICES", cap_words(sources).upper()),
        ("Bills", cap_words(sources)),
        ("Bill", src_cap),
        ("bills", sources),
        ("bill", source),
        ("refund_report.csv", spec["report"]),
        ("refund_summary.json", spec["summary"]),
        ("passes.csv", spec["source_file"]),
        ("refunds.csv", spec["action_file"]),
        ("pass_id", sid),
        ("PassID", f"{src_cap}ID"),
        ("guest_id", cid),
        ("Guest", cap_words(cid.removesuffix("_id"))),
        ("guest", cid.removesuffix("_id")),
        ("access_type", kind),
        ("AccessType", cap_words(kind)),
        ("Access_Types", f"{cap_words(kind)}s"),
        ("access type", kind.replace("_", " ")),
        ("visit_date", sdate),
        ("refund_date", adate),
        ("passes", sources),
        ("Passes", cap_words(sources)),
        ("pass", source),
        ("Pass", src_cap),
        ("refunds", actions),
        ("Refunds", cap_words(actions)),
        ("refund", action),
        ("Refund", act_cap),
        ("DAY", cat1),
        ("SEASON", cat2),
        ("VIP", cat3),
        ("DY", al1),
        ("SEA", al2),
        (" PSS", f" {spec['prefix']}"),
        ("PSS", spec["prefix"]),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"\bV\b", al3, text)
    text = re.sub(r"\bvip\b", cat3.lower(), text)
    text = re.sub(r"\bseason\b", cat2.lower(), text)
    text = re.sub(r"\bsea\b", al2.lower(), text)
    text = re.sub(r"\bdy\b", al1.lower(), text)
    text = re.sub(r"\bv\b", al3.lower(), text)
    text = text.replace("_season_", f"_{cat2.lower()}_")
    text = text.replace("_day_", f"_{cat1.lower()}_")
    text = text.replace("_sea_", f"_{al2.lower()}_")
    text = text.replace("_dy_", f"_{al1.lower()}_")
    text = text.replace("_vip_", f"_{cat3.lower()}_")
    text = text.replace("_v_", f"_{al3.lower()}_")
    text = text.replace("byclass", "bypass")
    text = text.replace(f"by{source}", "bypass")
    kind_words = kind.replace("_", " ")
    text = text.replace(f"criteria still {source}", "criteria still pass")
    text = text.replace(f"all prior gates {source}", "all prior gates pass")
    text = text.replace(f"canonical {source} {kind_words}", f"canonical {kind_words}")
    text = text.replace(f"selected canonical {source} {kind_words}", f"selected canonical {kind_words}")
    return text


def rename_known_files(dest: Path, spec: dict) -> None:
    renames = {
        "environment/data/passes.csv": f"environment/data/{spec['source_file']}",
        "environment/data/refunds.csv": f"environment/data/{spec['action_file']}",
        "environment/samples/bills_edge.csv": f"environment/samples/{spec['source_singular']}_edge.csv",
        "environment/samples/refunds_edge.csv": f"environment/samples/{spec['action_singular']}_edge.csv",
    }
    for old, new in renames.items():
        old_path = dest / old
        if old_path.exists():
            new_path = dest / new
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)


def scaffold(spec: dict) -> None:
    dest = ROOT / spec["slug"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(BASE, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
    rename_known_files(dest, spec)
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pyc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        path.write_text(replace_text(text, spec), encoding="utf-8", newline="\n")


def main() -> int:
    for spec in TASKS:
        scaffold(spec)
        print(spec["slug"])
    task_list = ROOT / "new_tasks_20260602_more10.txt"
    task_list.write_text("\n".join(spec["slug"] for spec in TASKS) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
