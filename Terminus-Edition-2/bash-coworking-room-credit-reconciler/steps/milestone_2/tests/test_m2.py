"""Verifier tests for the coworking room credit reconciliation batch."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
BOOKINGS = APP / "data" / "bookings.csv"
CREDITS = APP / "data" / "credits.csv"
ALIASES = APP / "config" / "plan_aliases.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
PROFILE = APP / "config" / "run_profile.ini"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
REPORT_FIELDS = ["booking_id", "member_id", "plan", "amount_cents", "status"]
SUMMARY_FIELDS = ["matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"]


def write_base_inputs(booking_rows, credit_rows, booking_header=None, credit_header=None):
    if booking_header is None:
        booking_header = "booking_id,member_id,amount_cents,status,plan"
    if credit_header is None:
        credit_header = "booking_id,member_id,amount_cents,plan"
    BOOKINGS.write_text(booking_header + "\n" + "\n".join(booking_rows) + "\n")
    CREDITS.write_text(credit_header + "\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_aliases(rows=None, header="alias,canonical,enabled"):
    if rows is None:
        rows = ["CC,PRIVATE,true", "INS,TEAM,true", "CA,HOTDESK,true", "FLEX,HOTDESK,false"]
    ALIASES.write_text(header + "\n" + "\n".join(rows) + "\n")


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REPORT_FIELDS
        rows = list(reader)
    summary = json.loads(SUMMARY.read_text())
    assert list(summary) == SUMMARY_FIELDS
    assert all(type(summary[key]) is int for key in SUMMARY_FIELDS)
    return rows, summary


class TestMilestone2:
    def test_milestone1_behavior_still_handles_header_reordering_and_amount_normalization(self):
        """Milestone 1 header reordering and amount normalization still pass with aliases enabled."""
        write_aliases()
        write_base_inputs(
            ["x,FINAL,TEAM,BOOK200000001,0000000990,MEMBER01", "y,FINAL,PRIVATE,BOOK200000002,1010,MEMBER02"],
            ["memo,BOOK200000001,990,MEMBER01,TEAM", "memo,BOOK200000002,0000001010,MEMBER02,PRIVATE"],
            booking_header="ignore,status,plan,booking_id,amount_cents,member_id",
            credit_header="note,booking_id,amount_cents,member_id,plan",
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 2000

    def test_runtime_aliases_match_and_emit_canonical_plans(self):
        """Runtime alias rows map CC, INS, and CA to canonical plans in matched output."""
        write_aliases()
        write_base_inputs(
            [
                "BOOK700000001,MEMBER01,3100,FINAL,PRIVATE",
                "BOOK700000002,MEMBER02,3200,FINAL,TEAM",
                "BOOK700000003,MEMBER03,3300,FINAL,HOTDESK",
                "BOOK700000004,MEMBER04,3400,FINAL,HOTDESK",
            ],
            [
                "BOOK700000001,MEMBER01,3100,cc",
                "BOOK700000002,MEMBER02,3200,INS",
                "BOOK700000003,MEMBER03,3300,CA",
                "BOOK700000004,MEMBER04,3400,UNKNOWN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["plan"] for row in rows] == ["PRIVATE", "TEAM", "HOTDESK", ""]
        assert summary["matched_amount_cents"] == 9600
        assert summary["unmatched_amount_cents"] == 3400

    def test_aliases_are_trimmed_case_folded_and_apply_on_both_sides(self):
        """Alias normalization trims, case-folds, and applies on both booking and credit sides."""
        write_aliases()
        write_base_inputs(
            [
                "BOOK710000001,MEMBER01,2100,FINAL, cc ",
                "BOOK710000002,MEMBER02,2200,FINAL,ins",
                "BOOK710000003,MEMBER03,2300,FINAL, Ca ",
            ],
            [
                "BOOK710000001,MEMBER01,2100, PRIVATE ",
                "BOOK710000002,MEMBER02,2200, InS ",
                "BOOK710000003,MEMBER03,2300,hotdesk",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["plan"] for row in rows] == ["PRIVATE", "TEAM", "HOTDESK"]
        assert summary == {"matched_count": 3, "matched_amount_cents": 6600, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_alias_config_is_runtime_data_not_hardcoded(self):
        """Custom alias file rows drive matching instead of hardcoded alias lists."""
        write_aliases(["DAYPASS,HOTDESK,true", "SUITE,PRIVATE,yes", "GROUP,TEAM,1"])
        write_base_inputs(
            [
                "BOOK720000001,MEMBER01,4100,FINAL,HOTDESK",
                "BOOK720000002,MEMBER02,4200,FINAL,PRIVATE",
                "BOOK720000003,MEMBER03,4300,FINAL,TEAM",
                "BOOK720000004,MEMBER04,4400,FINAL,HOTDESK",
            ],
            [
                "BOOK720000001,MEMBER01,4100,DAYPASS",
                "BOOK720000002,MEMBER02,4200,SUITE",
                "BOOK720000003,MEMBER03,4300,GROUP",
                "BOOK720000004,MEMBER04,4400,CA",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["plan"] for row in rows] == ["HOTDESK", "PRIVATE", "TEAM", ""]
        assert summary["matched_amount_cents"] == 12600
        assert summary["unmatched_amount_cents"] == 4400

    def test_alias_file_headers_are_case_insensitive_and_trimmed(self):
        """Alias CSV headers are recognized after trim and case folding."""
        write_aliases(
            ["DAY,HOTDESK,true"],
            header=" ALIAS , Canonical , ENABLED ",
        )
        write_base_inputs(
            ["BOOK800000001,MEMBER01,9000,FINAL,HOTDESK"],
            ["BOOK800000001,MEMBER01,9000,DAY"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["plan"] == "HOTDESK"
        assert summary["matched_amount_cents"] == 9000

    def test_alias_config_supports_header_reordering_extra_columns_and_disabled_rows(self):
        """Reordered alias columns and disabled rows apply only enabled mappings."""
        write_aliases(
            [
                "legacy-a,no,ignored,HOTDESK",
                "legacy-b,true,ignored,PRIVATE",
                "legacy-c,YES,ignored,TEAM",
            ],
            header="alias,enabled,owner,canonical",
        )
        write_base_inputs(
            ["BOOK730000001,MEMBER01,1111,FINAL,HOTDESK", "BOOK730000002,MEMBER02,2222,FINAL,PRIVATE", "BOOK730000003,MEMBER03,3333,FINAL,TEAM"],
            ["BOOK730000001,MEMBER01,1111,legacy-a", "BOOK730000002,MEMBER02,2222,legacy-b", "BOOK730000003,MEMBER03,3333,legacy-c"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED", "MATCHED"]
        assert [row["plan"] for row in rows] == ["", "PRIVATE", "TEAM"]
        assert summary["matched_amount_cents"] == 5555
        assert summary["unmatched_amount_cents"] == 1111

    def test_invalid_canonical_alias_rows_are_ignored(self):
        """Alias rows targeting non-canonical plans are ignored during normalization."""
        write_aliases(["BAD,MEETING,true", "GOOD,PRIVATE,true"])
        write_base_inputs(
            ["BOOK740000001,MEMBER01,5100,FINAL,MEETING", "BOOK740000002,MEMBER02,5200,FINAL,PRIVATE"],
            ["BOOK740000001,MEMBER01,5100,BAD", "BOOK740000002,MEMBER02,5200,GOOD"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[1]["plan"] == "PRIVATE"
        assert summary["matched_amount_cents"] == 5200

    def test_first_enabled_valid_duplicate_alias_row_wins(self):
        """When duplicate aliases exist, the first enabled valid row wins."""
        write_aliases(["X,PRIVATE,true", "X,TEAM,true"])
        write_base_inputs(
            ["BOOK750000001,MEMBER01,6100,FINAL,PRIVATE", "BOOK750000002,MEMBER02,6200,FINAL,TEAM"],
            ["BOOK750000001,MEMBER01,6100,X", "BOOK750000002,MEMBER02,6200,X"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["plan"] == "PRIVATE"
        assert summary["matched_amount_cents"] == 6100
        assert summary["unmatched_amount_cents"] == 6200

    def test_unknown_alias_does_not_fall_back_to_fuzzy_or_partial_matching(self):
        """Unknown aliases stay unmatched without fuzzy or partial plan fallback."""
        write_aliases(["TEAMLEGACY,TEAM,true"])
        write_base_inputs(
            ["BOOK760000001,MEMBER01,7100,FINAL,TEAM"],
            ["BOOK760000001,MEMBER01,7100,TEAMLEG"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan"] == ""
        assert summary["unmatched_amount_cents"] == 7100

    def test_aliases_do_not_break_booking_row_consumption(self):
        """Alias matching still consumes each booking row only once."""
        write_aliases(["DAY,HOTDESK,true"])
        write_base_inputs(
            ["BOOK770000001,MEMBER01,8100,FINAL,DAY"],
            ["BOOK770000001,MEMBER01,8100,HOTDESK", "BOOK770000001,MEMBER01,8100,DAY"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1

    def test_invalid_credit_amount_remains_unmatched_with_aliases(self):
        """Invalid credit amounts stay unmatched even when plan aliases resolve."""
        write_aliases(["DAY,HOTDESK,true"])
        write_base_inputs(["BOOK780000001,MEMBER01,900,FINAL,HOTDESK"], ["BOOK780000001,MEMBER01,00x,DAY"])
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["amount_cents"] == "00x"
        assert summary["unmatched_amount_cents"] == 0

    def test_blank_alias_rows_are_ignored(self):
        """Blank alias rows are skipped without breaking later valid mappings."""
        write_aliases([" ,PRIVATE,true", "GOOD,HOTDESK,true"])
        write_base_inputs(
            ["BOOK795000001,MEMBER01,5000,FINAL,HOTDESK"],
            ["BOOK795000001,MEMBER01,5000,GOOD"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["plan"] == "HOTDESK"
        assert summary["matched_amount_cents"] == 5000

    def test_alias_rows_missing_required_headers_do_not_apply(self):
        """Alias files missing required headers are ignored instead of partially applied."""
        write_aliases(["DAY,HOTDESK,true"], header="alias,owner,enabled")
        write_base_inputs(
            ["BOOK796000001,MEMBER01,5100,FINAL,HOTDESK"],
            ["BOOK796000001,MEMBER01,5100,DAY"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan"] == ""
        assert summary["matched_count"] == 0

    def test_alias_file_missing_enabled_header_keeps_canonical_self_mapping(self):
        """Without an enabled column, canonical plan tokens still self-map for matching."""
        write_aliases(["DAY,HOTDESK,ignored"], header="alias,canonical,owner")
        write_base_inputs(
            ["BOOK797000001,MEMBER01,5200,FINAL,HOTDESK"],
            ["BOOK797000001,MEMBER01,5200,HOTDESK"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["plan"] == "HOTDESK"
        assert summary["matched_amount_cents"] == 5200

    def test_alias_file_missing_alias_header_keeps_canonical_self_mapping(self):
        """Without an alias column, canonical plan tokens still self-map for matching."""
        write_aliases(["HOTDESK,PRIVATE,true"], header="canonical,enabled,owner")
        write_base_inputs(
            ["BOOK797000002,MEMBER01,5300,FINAL,PRIVATE"],
            ["BOOK797000002,MEMBER01,5300,PRIVATE"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["plan"] == "PRIVATE"
