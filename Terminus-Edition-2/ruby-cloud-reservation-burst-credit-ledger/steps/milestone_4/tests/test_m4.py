"""Verifier tests for policy-gated cloud reservation burst credit reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "seat_events.csv"
ACTION = APP / "data" / "credits.csv"
WINDOWS = APP / "config" / "windows.csv"
POLICY = APP / "config" / "sku_policy.csv"
REPORT = APP / "out" / "seat_credit_report.csv"
SUMMARY = APP / "out" / "seat_credit_summary.txt"


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows, policies):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["event_id", "account_id", "reservation_id", "sku_type", "amount", "reserve_ts", "status", "region"], source)
    write_csv(ACTION, ["credit_id", "event_id", "account_id", "reservation_id", "sku_type", "amount", "credit_ts", "reason", "region"], action)
    write_csv(WINDOWS, ["reservation_id", "open_ts", "close_ts", "state"], windows)
    write_csv(POLICY, ["region", "sku_type", "enabled", "min_amount", "max_amount", "priority"], policies)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone4:
    def test_region_policy_enabled_and_amount_range_gates(self):
        """Disabled policies and out-of-range amounts reject otherwise valid corrections."""
        write_inputs(
            [
                ["SRC-P1", "P1", "S-P", "CPU", "10", "20260528150000", "ALLOCATED", "R1"],
                ["SRC-P2", "P2", "S-P", "GPU", "30", "20260528150100", "ALLOCATED", "R2"],
                ["SRC-P3", "P3", "S-P", "MEM", "99", "20260528150200", "ALLOCATED", "R3"],
            ],
            [
                ["ACT-P1", "SRC-P1", "P1", "S-P", "CPU", "10", "20260528150600", "BURST", "R1"],
                ["ACT-P2", "SRC-P2", "P2", "S-P", "GPUF", "30", "20260528150600", "RECLAIM", "R2"],
                ["ACT-P3", "SRC-P3", "P3", "S-P", "MEMORY", "99", "20260528150600", "CORRECT", "R3"],
            ],
            [["S-P", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R1", "CPU", "true", "1", "20", "4"],
                ["R2", "GPU", "false", "1", "40", "9"],
                ["R3", "MEM", "enabled", "1", "50", "8"],
                ["*", "GPU", "true", "1", "999", "1"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["sku_type"] for row in rows] == ["CPU", "", ""]
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 2, "unmatched_amount": 129}
        assert SUMMARY.read_text().splitlines() == [
            "matched_count=1",
            "matched_amount=10",
            "unmatched_count=2",
            "unmatched_amount=129",
        ]

    def test_exact_region_policy_overrides_wildcard_fallback(self):
        """Exact region policies are authoritative even when wildcard rows would allow the sku_type."""
        write_inputs(
            [
                ["SRC-WILD", "PW", "S-W", "MEM", "20", "20260528150000", "ALLOCATED", "R-WILD"],
                ["SRC-OVERRIDE", "PO", "S-W", "CPU", "25", "20260528150100", "ALLOCATED", "R-LOCK"],
            ],
            [
                ["ACT-WILD", "SRC-WILD", "PW", "S-W", "MEMORY", "20", "20260528150600", "CORRECT", "R-WILD"],
                ["ACT-OVERRIDE", "SRC-OVERRIDE", "PO", "S-W", "CPU", "25", "20260528150600", "BURST", "R-LOCK"],
            ],
            [["S-W", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["*", "MEM", "TRUE", "1", "30", "2"],
                ["*", "CPU", "TRUE", "1", "30", "2"],
                ["R-LOCK", "CPU", "no", "1", "30", "9"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["sku_type"] for row in rows] == ["MEM", ""]
        assert summary == {"matched_count": 1, "matched_amount": 20, "unmatched_count": 1, "unmatched_amount": 25}

    def test_any_credit_matches_policy_allowed_source_and_emits_source_sku(self):
        """ANY can match an enabled canonical source sku_type but must report the source sku_type."""
        write_inputs(
            [
                ["SRC-ANY1", "PA", "S-A", "GPU", "44", "20260528150000", "ALLOCATED", "R-A"],
                ["SRC-ANY2", "PB", "S-A", "BAD", "45", "20260528150100", "ALLOCATED", "R-A"],
            ],
            [
                ["ACT-ANY1", "SRC-ANY1", "PA", "S-A", " any ", "44", "20260528150600", "BURST", "R-A"],
                ["ACT-ANY2", "SRC-ANY2", "PB", "S-A", "ANY", "45", "20260528150600", "BURST", "R-A"],
            ],
            [["S-A", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R-A", "GPU", "enabled", "1", "100", "7"],
                ["R-A", "BAD", "enabled", "1", "100", "99"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["sku_type"] for row in rows] == ["GPU", ""]
        assert summary == {"matched_count": 1, "matched_amount": 44, "unmatched_count": 1, "unmatched_amount": 45}

    def test_policy_equal_priority_and_timestamp_prefers_earliest_source_row(self):
        """When reserve_ts and policy priority tie, the earliest source input row must be consumed first."""
        write_inputs(
            [
                ["SRC-ORD", "PP", "S-PR", "CPU", "18", "20260528150000", "ALLOCATED", "R-PR"],
                ["SRC-ORD", "PP", "S-PR", "GPU", "18", "20260528150000", "ALLOCATED", "R-PR"],
                ["SRC-ORD", "PP", "S-PR", "MEM", "18", "20260528150000", "ALLOCATED", "R-PR"],
            ],
            [
                ["ACT-ORD1", "SRC-ORD", "PP", "S-PR", "ANY", "18", "20260528150600", "CORRECT", "R-PR"],
                ["ACT-ORD2", "SRC-ORD", "PP", "S-PR", "ANY", "18", "20260528150610", "CORRECT", "R-PR"],
            ],
            [["S-PR", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R-PR", "CPU", "true", "1", "20", "7"],
                ["R-PR", "GPU", "true", "1", "20", "7"],
                ["R-PR", "MEM", "true", "1", "20", "7"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["CPU", "GPU"]
        assert summary == {"matched_count": 2, "matched_amount": 36, "unmatched_count": 0, "unmatched_amount": 0}

    def test_policy_priority_breaks_equal_timestamp_candidates_before_row_order(self):
        """For equal reserve_ts candidates, higher policy priority wins before earliest row order."""
        write_inputs(
            [
                ["SRC-PR", "PP", "S-PR", "CPU", "12", "20260528150000", "ALLOCATED", "R-PR"],
                ["SRC-PR", "PP", "S-PR", "GPU", "12", "20260528150000", "ALLOCATED", "R-PR"],
                ["SRC-PR", "PP", "S-PR", "MEM", "12", "20260528145959", "ALLOCATED", "R-PR"],
            ],
            [
                ["ACT-PR1", "SRC-PR", "PP", "S-PR", "ANY", "12", "20260528150600", "CORRECT", "R-PR"],
                ["ACT-PR2", "SRC-PR", "PP", "S-PR", "ANY", "12", "20260528150610", "CORRECT", "R-PR"],
                ["ACT-PR3", "SRC-PR", "PP", "S-PR", "ANY", "12", "20260528150620", "CORRECT", "R-PR"],
            ],
            [["S-PR", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R-PR", "CPU", "true", "1", "20", "4"],
                ["R-PR", "GPU", "true", "1", "20", "9"],
                ["R-PR", "MEM", "true", "1", "20", "99"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["GPU", "CPU", "MEM"]
        assert summary == {"matched_count": 3, "matched_amount": 36, "unmatched_count": 0, "unmatched_amount": 0}

    def test_policy_logic_does_not_bypass_window_or_region_gates(self):
        """ANY and policy eligibility must still honor prior window and region gates."""
        write_inputs(
            [
                ["SRC-G1", "PG1", "S-G1", "CPU", "31", "20260528150000", "ALLOCATED", "R-G"],
                ["SRC-G2", "PG2", "S-G2", "GPU", "32", "20260528150000", "ALLOCATED", "R-G"],
            ],
            [
                ["ACT-G1", "SRC-G1", "PG1", "S-G1", "ANY", "31", "20260528150600", "BURST", "R-OTHER"],
                ["ACT-G2", "SRC-G2", "PG2", "S-G2", "ANY", "32", "20260528153100", "BURST", "R-G"],
            ],
            [
                ["S-G1", "20260528145900", "20260528153000", "OPEN"],
                ["S-G2", "20260528145900", "20260528153000", "OPEN"],
            ],
            [
                ["R-G", "CPU", "true", "1", "40", "5"],
                ["R-G", "GPU", "true", "1", "40", "5"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["sku_type"] for row in rows] == ["", ""]
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 63}

    def test_prior_milestone_gates_still_reject_with_valid_policies(self):
        """Policy rows must not bypass status, reason, or consumption gates from earlier milestones."""
        write_inputs(
            [
                ["SRC-R1", "PR1", "S-R", "CPU", "10", "20260528150000", "BAD", "R1"],
                ["SRC-R2", "PR2", "S-R", "GPU", "20", "20260528150100", "ALLOCATED", "R1"],
            ],
            [
                ["ACT-R1", "SRC-R1", "PR1", "S-R", "ANY", "10", "20260528150600", "BURST", "R1"],
                ["ACT-R2", "SRC-R2", "PR2", "S-R", "ANY", "20", "20260528150600", "INFO", "R1"],
                ["ACT-R3", "SRC-R2", "PR2", "S-R", "ANY", "20", "20260528150610", "BURST", "R1"],
            ],
            [["S-R", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R1", "CPU", "true", "1", "50", "5"],
                ["R1", "GPU", "true", "1", "50", "5"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["", "", "GPU"]
        assert summary == {"matched_count": 1, "matched_amount": 20, "unmatched_count": 2, "unmatched_amount": 30}

    def test_non_numeric_policy_min_amount_is_ignored(self):
        """Policy rows with non-numeric min_amount values must be ignored."""
        write_inputs(
            [["SRC-NP", "PN", "S-NP", "CPU", "15", "20260528150000", "ALLOCATED", "R-NP"]],
            [["ACT-NP", "SRC-NP", "PN", "S-NP", "ANY", "15", "20260528150600", "BURST", "R-NP"]],
            [["S-NP", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["*", "CPU", "true", "abc", "20", "4"],
                ["*", "CPU", "true", "1", "20", "5"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "CPU"
        assert summary == {"matched_count": 1, "matched_amount": 15, "unmatched_count": 0, "unmatched_amount": 0}

    def test_non_numeric_policy_max_amount_is_ignored(self):
        """Policy rows with non-numeric max_amount values must be ignored."""
        write_inputs(
            [["SRC-NP", "PN", "S-NP", "GPU", "15", "20260528150000", "ALLOCATED", "R-NP"]],
            [["ACT-NP", "SRC-NP", "PN", "S-NP", "ANY", "15", "20260528150600", "BURST", "R-NP"]],
            [["S-NP", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["*", "GPU", "true", "1", "xyz", "4"],
                ["*", "GPU", "true", "1", "20", "5"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "GPU"
        assert summary == {"matched_count": 1, "matched_amount": 15, "unmatched_count": 0, "unmatched_amount": 0}

    def test_non_numeric_policy_priority_is_ignored(self):
        """Policy rows with non-numeric priority values must be ignored."""
        write_inputs(
            [["SRC-NP", "PN", "S-NP", "MEM", "15", "20260528150000", "ALLOCATED", "R-NP"]],
            [["ACT-NP", "SRC-NP", "PN", "S-NP", "ANY", "15", "20260528150600", "BURST", "R-NP"]],
            [["S-NP", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["*", "MEM", "true", "1", "20", "N/A"],
                ["*", "MEM", "true", "1", "20", "5"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "MEM"
        assert summary == {"matched_count": 1, "matched_amount": 15, "unmatched_count": 0, "unmatched_amount": 0}

    def test_only_invalid_policy_rows_leave_correction_unmatched(self):
        """When every policy row is malformed, the correction must stay UNMATCHED."""
        write_inputs(
            [["SRC-BAD", "PB", "S-BAD", "CPU", "15", "20260528150000", "ALLOCATED", "R-BAD"]],
            [["ACT-BAD", "SRC-BAD", "PB", "S-BAD", "ANY", "15", "20260528150600", "BURST", "R-BAD"]],
            [["S-BAD", "20260528145900", "20260528153000", "OPEN"]],
            [["*", "CPU", "true", "abc", "20", "4"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["sku_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 15}

    def test_policy_sku_type_alias_normalization(self):
        """Policy sku_type aliases must normalize with the same rules as source rows."""
        write_inputs(
            [["SRC-PA", "PPA", "S-PA", "CPU", "18", "20260528150000", "ALLOCATED", "R-PA"]],
            [["ACT-PA", "SRC-PA", "PPA", "S-PA", "ANY", "18", "20260528150600", "BURST", "R-PA"]],
            [["S-PA", "20260528145900", "20260528153000", "OPEN"]],
            [["R-PA", "C", "true", "1", "20", "4"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "CPU"
        assert summary == {"matched_count": 1, "matched_amount": 18, "unmatched_count": 0, "unmatched_amount": 0}

    def test_policy_region_trim_and_case_fold_matching(self):
        """Policy region values must trim and case-fold to match source and correction regions."""
        write_inputs(
            [["SRC-RN", "PRN", "S-RN", "CPU", "16", "20260528150000", "ALLOCATED", "R-PA"]],
            [["ACT-RN", "SRC-RN", "PRN", "S-RN", "ANY", "16", "20260528150600", "BURST", "R-PA"]],
            [["S-RN", "20260528145900", "20260528153000", "OPEN"]],
            [[" r-Pa ", "CPU", "true", "1", "20", "4"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "CPU"
        assert summary == {"matched_count": 1, "matched_amount": 16, "unmatched_count": 0, "unmatched_amount": 0}

    def test_named_sku_type_requires_exact_match(self):
        """Named correction sku_types cannot cross-match a different canonical source sku_type."""
        write_inputs(
            [["SRC-N1", "PN1", "S-N", "GPU", "22", "20260528150000", "ALLOCATED", "R-N"]],
            [["ACT-N1", "SRC-N1", "PN1", "S-N", "CPU", "22", "20260528150600", "BURST", "R-N"]],
            [["S-N", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R-N", "CPU", "true", "1", "50", "5"],
                ["R-N", "GPU", "true", "1", "50", "5"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["sku_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 22}

    def test_enabled_state_synonyms_yes_y_and_one(self):
        """Policy enabled states yes, y, and 1 must be treated as enabled case-insensitively."""
        write_inputs(
            [
                ["SRC-E1", "PE1", "S-E", "CPU", "11", "20260528150000", "ALLOCATED", "R-E1"],
                ["SRC-E2", "PE2", "S-E", "GPU", "12", "20260528150100", "ALLOCATED", "R-E2"],
                ["SRC-E3", "PE3", "S-E", "MEM", "13", "20260528150200", "ALLOCATED", "R-E3"],
            ],
            [
                ["ACT-E1", "SRC-E1", "PE1", "S-E", "ANY", "11", "20260528150600", "BURST", "R-E1"],
                ["ACT-E2", "SRC-E2", "PE2", "S-E", "ANY", "12", "20260528150600", "RECLAIM", "R-E2"],
                ["ACT-E3", "SRC-E3", "PE3", "S-E", "ANY", "13", "20260528150600", "CORRECT", "R-E3"],
            ],
            [
                ["S-E", "20260528145900", "20260528153000", "OPEN"],
            ],
            [
                ["R-E1", "CPU", "yes", "1", "20", "4"],
                ["R-E2", "GPU", "1", "1", "20", "4"],
                ["R-E3", "MEM", " y ", "1", "20", "4"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["CPU", "GPU", "MEM"]
        assert summary == {"matched_count": 3, "matched_amount": 36, "unmatched_count": 0, "unmatched_amount": 0}

    def test_empty_policy_file_leaves_correction_unmatched(self):
        """A header-only policy file must not enable any source SKU type."""
        write_inputs(
            [["SRC-EMPTY", "PE", "S-E", "CPU", "10", "20260528150000", "ALLOCATED", "R-E"]],
            [["ACT-EMPTY", "SRC-EMPTY", "PE", "S-E", "ANY", "10", "20260528150600", "BURST", "R-E"]],
            [["S-E", "20260528145900", "20260528153000", "OPEN"]],
            [],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["sku_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}

    def test_policy_amount_range_boundaries_are_inclusive(self):
        """Amounts equal to policy minimum and maximum boundaries must remain eligible."""
        write_inputs(
            [
                ["SRC-MIN", "PB1", "S-B", "CPU", "10", "20260528150000", "ALLOCATED", "R-B"],
                ["SRC-MAX", "PB2", "S-B", "GPU", "20", "20260528150100", "ALLOCATED", "R-B"],
            ],
            [
                ["ACT-MIN", "SRC-MIN", "PB1", "S-B", "ANY", "10", "20260528150600", "BURST", "R-B"],
                ["ACT-MAX", "SRC-MAX", "PB2", "S-B", "ANY", "20", "20260528150700", "RECLAIM", "R-B"],
            ],
            [["S-B", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["R-B", "CPU", "true", "10", "20", "4"],
                ["R-B", "GPU", "true", "10", "20", "4"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["CPU", "GPU"]
        assert summary == {"matched_count": 2, "matched_amount": 30, "unmatched_count": 0, "unmatched_amount": 0}
