
import csv
import os
import subprocess
from pathlib import Path

APP = Path('/app')
HOLDS = APP / 'data' / 'holds.csv'
ACTIONS = APP / 'data' / 'disbursements.csv'
WINDOWS = APP / 'config' / 'windows.csv'
PACKAGES = APP / 'config' / 'closing_packages.csv'
BALANCES = APP / 'data' / 'trust_balances.csv'
CONTROLS = APP / 'config' / 'control_totals.csv'
OUT = APP / 'out'
REPORT = OUT / 'disbursement_report.csv'
SUMMARY = OUT / 'disbursement_summary.txt'
GROUPS = OUT / 'closing_group_report.csv'
BALANCE_AFTER = OUT / 'trust_balance_after.csv'
COMMITS = OUT / 'escrow_commit_ledger.csv'
CHECKPOINT = OUT / 'restart_checkpoint.txt'


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(holds, actions, windows, packages=None, balances=None, controls=None):
    write_csv(HOLDS, ['escrow_id','payee_id','trust_id','kind','amount','source_ts','status','location'], holds)
    write_csv(ACTIONS, ['action_id','closing_id','escrow_id','payee_id','trust_id','kind','amount','action_ts','reason','location'], actions)
    write_csv(WINDOWS, ['trust_id','open_ts','close_ts','state'], windows)
    if packages is not None:
        write_csv(PACKAGES, ['closing_id','escrow_id','trust_id','expected_total','required_kinds','package_state'], packages)
    if balances is not None:
        write_csv(BALANCES, ['trust_id','opening_balance'], balances)
    if controls is not None:
        write_csv(CONTROLS, ['trust_id','expected_group_count','expected_amount'], controls)
    OUT.mkdir(parents=True, exist_ok=True)
    for path in [REPORT, SUMMARY, GROUPS, BALANCE_AFTER, COMMITS, CHECKPOINT]:
        path.unlink(missing_ok=True)


def rows(path):
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def summary():
    data = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split('=', 1)
        data[key] = int(value)
    return data


def run_ok(env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(['ruby', '/app/app/reconcile.rb'], cwd=APP, env=merged_env, check=True, timeout=60)


def run_fail(env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(['ruby', '/app/app/reconcile.rb'], cwd=APP, env=merged_env, check=False, timeout=60)


class TestMilestone1:
    def test_strict_identity_status_window_and_no_alias_contract(self):
        """Only full-key canonical SELLER/BROKER rows inside an open window may match."""
        write_inputs(
            [
                ['ESC-1','PAY-1','TRUST-A','SELLER','100','20260613100000','HELD','LOC-A'],
                ['ESC-2','PAY-2','TRUST-A','SELLER','200','20260613100100','RELEASED','LOC-A'],
                ['ESC-3','PAY-3','TRUST-A','BROKER','300','20260613100200','HELD','LOC-B'],
                ['ESC-4','PAY-4','TRUST-A','ESCROWFEE','400','20260613100300','HELD','LOC-C'],
            ],
            [
                ['ACT-1','PKG-1','ESC-1','PAY-1','TRUST-A','SELLER','100','20260613100500','CLOSE','LOC-A'],
                ['ACT-2','PKG-2','ESC-2','PAY-2','TRUST-A','SELLER','200','20260613100600','CLOSE','LOC-A'],
                ['ACT-3','PKG-3','ESC-3','PAY-X','TRUST-A','BROKER','300','20260613100600','CORRECT','LOC-B'],
                ['ACT-4','PKG-4','ESC-4','PAY-4','TRUST-A','ESCROWFEE','400','20260613100600','RELEASE','LOC-C'],
                ['ACT-5','PKG-5','ESC-3','PAY-3','TRUST-A','BROKER','300','20260613110001','RELEASE','LOC-B'],
            ],
            [['TRUST-A','20260613095900','20260613110000','OPEN']],
        )
        run_ok()
        report = rows(REPORT)
        assert [r['status'] for r in report] == ['MATCHED','UNMATCHED','UNMATCHED','UNMATCHED','UNMATCHED']
        assert [r['kind'] for r in report] == ['SELLER','','','','']
        assert [r['reason'] for r in report] == ['CLOSE','CLOSE','CORRECT','RELEASE','RELEASE']
        assert summary() == {'matched_count': 1, 'matched_amount': 100, 'unmatched_count': 4, 'unmatched_amount': 1200}

    def test_latest_eligible_source_is_consumed_once_without_prefix_matching(self):
        """Source selection must use full IDs, latest source_ts, tie by input order, and one-time consumption."""
        write_inputs(
            [
                ['ESC-DUPE','PAY-1','TRUST-B','BROKER','50','20260613100000','HELD','LOC-A'],
                ['ESC-DUPE','PAY-1','TRUST-B','BROKER','50','20260613100200','HELD','LOC-A'],
                ['ESC-DUPE-EXTRA','PAY-1','TRUST-B','BROKER','50','20260613100300','HELD','LOC-A'],
            ],
            [
                ['ACT-A','PKG-A','ESC-DUPE','PAY-1','TRUST-B','BROKER','50','20260613100500','CLOSE','LOC-A'],
                ['ACT-B','PKG-B','ESC-DUPE','PAY-1','TRUST-B','BROKER','50','20260613100600','CLOSE','LOC-A'],
                ['ACT-C','PKG-C','ESC-DUPE','PAY-1','TRUST-B','BROKER','50','20260613100700','CLOSE','LOC-A'],
            ],
            [['TRUST-B','20260613095900','20260613103000','OPEN']],
        )
        run_ok()
        report = rows(REPORT)
        assert [r['status'] for r in report] == ['MATCHED','MATCHED','UNMATCHED']
        assert [r['kind'] for r in report] == ['BROKER','BROKER','']
        assert summary() == {'matched_count': 2, 'matched_amount': 100, 'unmatched_count': 1, 'unmatched_amount': 50}

    def test_hold_selection_prefers_latest_source_ts_for_matching_amount(self):
        """Choosing the latest hold first must leave the earlier hold for an earlier second action."""
        write_inputs(
            [
                ['ESC-TIE','PAY','TRUST-T','BROKER','50','20260613100000','HELD','LOC-A'],
                ['ESC-TIE','PAY','TRUST-T','BROKER','50','20260613100200','HELD','LOC-A'],
            ],
            [
                ['ACT-LATEST','PKG-1','ESC-TIE','PAY','TRUST-T','BROKER','50','20260613100500','CLOSE','LOC-A'],
                ['ACT-EARLY','PKG-2','ESC-TIE','PAY','TRUST-T','BROKER','50','20260613100100','CORRECT','LOC-A'],
            ],
            [['TRUST-T','20260613095900','20260613103000','OPEN']],
        )
        run_ok()
        report = {r['action_id']: r for r in rows(REPORT)}
        assert report['ACT-LATEST']['status'] == 'MATCHED'
        assert report['ACT-EARLY']['status'] == 'MATCHED'
        assert report['ACT-LATEST']['reason'] == 'CLOSE'
        assert report['ACT-EARLY']['reason'] == 'CORRECT'
        assert summary() == {'matched_count': 2, 'matched_amount': 100, 'unmatched_count': 0, 'unmatched_amount': 0}

    def test_equal_source_timestamps_consume_duplicate_holds_in_input_order(self):
        """Equal-timestamp physical rows remain independently consumable with deterministic row order."""
        write_inputs(
            [
                ['ESC-EQUAL','PAY','TRUST-Q','SELLER','75','20260613100000','HELD','LOC-Q'],
                ['ESC-EQUAL','PAY','TRUST-Q','SELLER','75','20260613100000','HELD','LOC-Q'],
            ],
            [
                ['ACT-Q1','PKG-Q1','ESC-EQUAL','PAY','TRUST-Q','SELLER','75','20260613100500','CLOSE','LOC-Q'],
                ['ACT-Q2','PKG-Q2','ESC-EQUAL','PAY','TRUST-Q','SELLER','75','20260613100600','RELEASE','LOC-Q'],
                ['ACT-Q3','PKG-Q3','ESC-EQUAL','PAY','TRUST-Q','SELLER','75','20260613100700','CORRECT','LOC-Q'],
            ],
            [['TRUST-Q','20260613095900','20260613103000','OPEN']],
        )
        run_ok()
        report = rows(REPORT)
        assert [r['status'] for r in report] == ['MATCHED', 'MATCHED', 'UNMATCHED']
        assert [r['reason'] for r in report] == ['CLOSE', 'RELEASE', 'CORRECT']
        assert summary() == {'matched_count': 2, 'matched_amount': 150, 'unmatched_count': 1, 'unmatched_amount': 75}

    def test_hold_source_timestamp_must_be_inside_open_window(self):
        """A hold whose source_ts falls outside the OPEN window must not match even when other gates pass."""
        write_inputs(
            [
                ['ESC-OOW','PAY-OOW','TRUST-X','SELLER','100','20260613090000','HELD','LOC-A'],
            ],
            [
                ['ACT-OOW','PKG-OOW','ESC-OOW','PAY-OOW','TRUST-X','SELLER','100','20260613100000','CLOSE','LOC-A'],
            ],
            [['TRUST-X','20260613095900','20260613110000','OPEN']],
        )
        run_ok()
        report = rows(REPORT)
        assert report[0]['status'] == 'UNMATCHED'
        assert report[0]['kind'] == ''
        assert summary() == {'matched_count': 0, 'matched_amount': 0, 'unmatched_count': 1, 'unmatched_amount': 100}

    def test_alias_kinds_are_not_resolved_in_milestone_one(self):
        """Milestone 1 must reject alias kind values such as SLR even when the hold kind is canonical SELLER."""
        write_inputs(
            [
                ['ESC-A','PAY-A','TRUST-A','SELLER','100','20260613100000','HELD','LOC-A'],
            ],
            [
                ['ACT-A','PKG-A','ESC-A','PAY-A','TRUST-A','SLR','100','20260613100500','CLOSE','LOC-A'],
            ],
            [['TRUST-A','20260613095900','20260613110000','OPEN']],
        )
        run_ok()
        report = rows(REPORT)
        assert report[0]['status'] == 'UNMATCHED'
        assert report[0]['kind'] == ''

    def test_matching_guards_reject_invalid_reason_kind_time_location_and_window_close(self):
        """Reason, kind equality, temporal ordering, location, and window close must all be enforced."""
        write_inputs(
            [
                ['ESC-R','PAY-R','TRUST-R','SELLER','100','20260613100500','HELD','LOC-A'],
                ['ESC-K','PAY-K','TRUST-R','SELLER','200','20260613100000','HELD','LOC-A'],
                ['ESC-L','PAY-L','TRUST-R','SELLER','300','20260613100000','HELD','LOC-A'],
                ['ESC-T','PAY-T','TRUST-R','SELLER','400','20260613100000','HELD','LOC-A'],
                ['ESC-W','PAY-W','TRUST-R','SELLER','500','20260613100000','HELD','LOC-A'],
            ],
            [
                ['ACT-R','PKG-R','ESC-R','PAY-R','TRUST-R','SELLER','100','20260613100600','REFUND','LOC-A'],
                ['ACT-K','PKG-K','ESC-K','PAY-K','TRUST-R','BROKER','200','20260613100500','CLOSE','LOC-A'],
                ['ACT-L','PKG-L','ESC-L','PAY-L','TRUST-R','SELLER','300','20260613100500','CLOSE','LOC-B'],
                ['ACT-T','PKG-T','ESC-T','PAY-T','TRUST-R','SELLER','400','20260613100000','CLOSE','LOC-A'],
                ['ACT-W','PKG-W','ESC-W','PAY-W','TRUST-R','SELLER','500','20260613110001','CLOSE','LOC-A'],
            ],
            [['TRUST-R','20260613095900','20260613110000','OPEN']],
        )
        run_ok()
        report = rows(REPORT)
        assert [r['status'] for r in report] == ['UNMATCHED'] * 5
        assert summary() == {'matched_count': 0, 'matched_amount': 0, 'unmatched_count': 5, 'unmatched_amount': 1500}
