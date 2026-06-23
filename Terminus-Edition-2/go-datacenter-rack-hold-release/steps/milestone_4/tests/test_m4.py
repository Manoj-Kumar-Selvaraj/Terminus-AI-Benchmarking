"""Milestone 4 verifier tests for large-batch audit output."""

import csv
import subprocess
from collections import defaultdict
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
ALIASES = APP / "config" / "access_tier_aliases.csv"
REPORT = APP / "out" / "rack_release_report.csv"
SUMMARY = APP / "out" / "rack_release_summary.txt"
REJECTIONS = APP / "out" / "rack_release_rejections.csv"
AUDIT = APP / "out" / "rack_release_audit.csv"


def build_program():
    """Compile the submitted Go reconciler."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write a verifier CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows, aliases):
    """Overwrite all runtime inputs."""
    write_csv(SOURCE, ["hold_id", "asset_id", "aisle_id", "access_tier", "amount", "hold_ts", "status", "rack"], source)
    write_csv(ACTION, ["release_id", "hold_id", "asset_id", "aisle_id", "access_tier", "amount", "release_ts", "reason", "rack"], action)
    write_csv(WINDOWS, ["aisle_id", "open_ts", "close_ts", "state"], windows)
    write_csv(ALIASES, ["alias", "canonical"], aliases)
    for path in (REPORT, SUMMARY, REJECTIONS, AUDIT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)


def read_outputs():
    """Run the reconciler and parse all milestone 4 outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        report = list(csv.DictReader(handle))
    with REJECTIONS.open(newline="") as handle:
        rejections = list(csv.DictReader(handle))
    with AUDIT.open(newline="") as handle:
        audit = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return report, summary, rejections, audit


def canonical_amount(value):
    """Return positive int for canonical amount strings, otherwise zero for unmatched totals."""
    if not value or value == "0" or (len(value) > 1 and value.startswith("0")) or not value.isdigit():
        return 0
    return int(value)


def expected_audit_from_report(report):
    """Compute expected audit rows from the report contract."""
    buckets = defaultdict(lambda: {"total_releases": 0, "matched_count": 0, "unmatched_count": 0, "matched_amount": 0, "unmatched_amount": 0})
    for row in report:
        bucket = buckets[row["aisle_id"]]
        bucket["total_releases"] += 1
        amount = canonical_amount(row["amount"])
        if row["status"] == "MATCHED":
            bucket["matched_count"] += 1
            bucket["matched_amount"] += amount
        else:
            bucket["unmatched_count"] += 1
            bucket["unmatched_amount"] += amount
    return [
        {"aisle_id": aisle, **{key: str(value) for key, value in buckets[aisle].items()}}
        for aisle in sorted(buckets)
    ]


def test_large_runtime_batch_audit_reconciles_with_summary_and_report():
    """Hundreds of runtime rows should produce sorted per-aisle audit totals that match the report."""
    build_program()
    aliases = [["FIRE", "HOT"], ["COZY", "WARM"], ["VAULT", "COLD"], ["BADMAP", "ARCHIVE"]]
    windows = [
        ["A-BULK-1", "20260528100000", "20260528160000", "OPEN"],
        ["A-BULK-2", "20260528100000", "20260528160000", "open"],
        ["A-BULK-3", "20260528100000", "20260528123000", "OPEN"],
        ["A-BULK-3", "20260528123030", "20260528170000", "OPEN"],
        ["A-BULK-4", "20260528100000", "20260528160000", "CLOSED"],
        ["A-BULK-5", "bad-open", "20260528160000", "OPEN"],
    ]
    holds = []
    releases = []
    tiers = [("FIRE", "HOT"), ("COZY", "WARM"), ("VAULT", "COLD")]
    reasons = ["DECOMM", "MIGRATE", "OVERRIDE"]
    for i in range(1, 181):
        aisle = f"A-BULK-{1 + (i % 5)}"
        alias, canonical = tiers[i % 3]
        amount = str(1000 + i)
        minute = i % 60
        second = i % 50
        hold_ts = f"2026052811{minute:02d}{second:02d}"
        release_ts = f"2026052812{minute:02d}{second:02d}"
        status = "LOCKED" if i % 17 else "HELD"
        rack = f"R{i:03d}"
        holds.append([f"SRC-BULK-{i:03d}", f"ASSET-{i:03d}", aisle, alias, amount, hold_ts, status, rack])
        rel_amount = amount
        rel_ts = release_ts
        rel_reason = reasons[i % 3]
        rel_rack = rack
        if i % 19 == 0:
            rel_amount = f"0{amount}"
        if i % 23 == 0:
            rel_ts = "bad-release"
        if i % 29 == 0:
            rel_reason = "INFO"
        if i % 31 == 0:
            rel_rack = "WRONG-RACK"
        releases.append([f"REL-BULK-{i:03d}", f"SRC-BULK-{i:03d}", f"ASSET-{i:03d}", aisle, canonical, rel_amount, rel_ts, rel_reason, rel_rack])

    write_inputs(holds, releases, windows, aliases)
    report, summary, rejections, audit = read_outputs()

    assert len(report) == 180
    assert len(rejections) == sum(1 for row in report if row["status"] == "UNMATCHED")
    assert audit == expected_audit_from_report(report)
    assert sum(int(row["matched_count"]) for row in audit) == summary["matched_count"]
    assert sum(int(row["unmatched_count"]) for row in audit) == summary["unmatched_count"]
    assert sum(int(row["matched_amount"]) for row in audit) == summary["matched_amount"]
    assert sum(int(row["unmatched_amount"]) for row in audit) == summary["unmatched_amount"]
    assert [row["aisle_id"] for row in audit] == sorted(row["aisle_id"] for row in audit)
    assert any(row["code"] == "BAD_RELEASE_AMOUNT" for row in rejections)
    assert any(row["code"] == "BAD_RELEASE_TS" for row in rejections)
    assert any(row["code"] == "BAD_REASON" for row in rejections)
    assert any(row["code"] == "NO_SOURCE_IDENTITY" for row in rejections)
    assert any(row["code"] == "WINDOW_INELIGIBLE" for row in rejections)


def test_audit_includes_only_aisles_from_correction_input_and_uses_invalid_amount_zero():
    """Audit rows are driven by correction aisles, and invalid unmatched amounts contribute zero."""
    build_program()
    write_inputs(
        [
            ["SRC-AUD-1", "ASSET-1", "A-AUD-2", "HOT", "10", "20260528120000", "LOCKED", "R1"],
            ["SRC-AUD-2", "ASSET-2", "A-AUD-1", "WARM", "11", "20260528120000", "LOCKED", "R2"],
            ["SRC-AUD-NO-REL", "ASSET-X", "A-AUD-X", "HOT", "99", "20260528120000", "LOCKED", "RX"],
        ],
        [
            ["REL-AUD-1", "SRC-AUD-1", "ASSET-1", "A-AUD-2", "HOT", "10", "20260528120100", "DECOMM", "R1"],
            ["REL-AUD-2", "SRC-AUD-2", "ASSET-2", "A-AUD-1", "WARM", "+11", "20260528120100", "MIGRATE", "R2"],
            ["REL-AUD-3", "SRC-MISSING", "ASSET-3", "A-AUD-1", "HOT", "12", "20260528120100", "DECOMM", "R3"],
        ],
        [["A-AUD-1", "20260528115900", "20260528123000", "OPEN"], ["A-AUD-2", "20260528115900", "20260528123000", "OPEN"]],
        [["IN", "HOT"], ["CU", "WARM"], ["SE", "COLD"]],
    )
    report, summary, _, audit = read_outputs()

    assert [row["aisle_id"] for row in audit] == ["A-AUD-1", "A-AUD-2"]
    assert audit == expected_audit_from_report(report)
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 2, "unmatched_amount": 12}
