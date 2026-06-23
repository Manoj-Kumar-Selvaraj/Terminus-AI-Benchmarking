
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


class TestMilestone3:
    def test_trust_funding_is_consumed_only_by_cleared_groups(self):
        """Trust balance should fund complete groups in order and hold later groups when funds run out."""
        write_inputs(
            [
                ['ESC-A','PAY-S','TRUST-E','SELLER','400','20260613100000','HELD','LOC-1'],
                ['ESC-B','PAY-S','TRUST-E','SELLER','350','20260613100100','HELD','LOC-2'],
                ['ESC-C','PAY-S','TRUST-F','SELLER','100','20260613100200','HELD','LOC-3'],
            ],
            [
                ['ACT-A','CLOSE-A','ESC-A','PAY-S','TRUST-E','SELLER','400','20260613101000','CLOSE','LOC-1'],
                ['ACT-B','CLOSE-B','ESC-B','PAY-S','TRUST-E','SELLER','350','20260613101100','CLOSE','LOC-2'],
                ['ACT-C','CLOSE-C','ESC-C','PAY-S','TRUST-F','SELLER','100','20260613101200','CLOSE','LOC-3'],
            ],
            [['TRUST-E','20260613095900','20260613103000','OPEN'], ['TRUST-F','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-A','ESC-A','TRUST-E','400','SELLER','OPEN'],
                ['CLOSE-B','ESC-B','TRUST-E','350','SELLER','OPEN'],
                ['CLOSE-C','ESC-C','TRUST-F','100','SELLER','OPEN'],
            ],
            [['TRUST-E','500'], ['TRUST-F','100']],
            [['TRUST-E','2','750'], ['TRUST-F','1','100']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-A']['status'] == 'CLEARED'
        assert groups['CLOSE-B']['status'] == 'HELD'
        assert groups['CLOSE-B']['reason'] == 'INSUFFICIENT_FUNDS'
        assert groups['CLOSE-C']['status'] == 'CLEARED'
        balances = {r['trust_id']: r['balance'] for r in rows(BALANCE_AFTER)}
        assert balances == {'TRUST-E': '100', 'TRUST-F': '0'}

    def test_control_total_mismatch_holds_all_clearable_groups_for_trust(self):
        """Operator control totals must reconcile before any otherwise complete group for that trust clears."""
        write_inputs(
            [
                ['ESC-X','PAY-S','TRUST-G','SELLER','100','20260613100000','HELD','LOC-1'],
                ['ESC-Y','PAY-S','TRUST-G','SELLER','200','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-X','CLOSE-X','ESC-X','PAY-S','TRUST-G','SELLER','100','20260613101000','CLOSE','LOC-1'],
                ['ACT-Y','CLOSE-Y','ESC-Y','PAY-S','TRUST-G','SELLER','200','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-G','20260613095900','20260613103000','OPEN']],
            [['CLOSE-X','ESC-X','TRUST-G','100','SELLER','OPEN'], ['CLOSE-Y','ESC-Y','TRUST-G','200','SELLER','OPEN']],
            [['TRUST-G','1000']],
            [['TRUST-G','1','300']],
        )
        run_ok()
        assert {r['status'] for r in rows(GROUPS)} == {'HELD'}
        assert {r['reason'] for r in rows(GROUPS)} == {'CONTROL_TOTAL_MISMATCH'}
        assert rows(BALANCE_AFTER) == [{'trust_id': 'TRUST-G', 'balance': '1000'}]

    def test_held_packages_do_not_consume_trust_balance(self):
        """A package held for package-state reasons must not reduce trust balance for later clearable groups."""
        write_inputs(
            [
                ['ESC-A','PAY','TRUST-H','SELLER','200','20260613100000','HELD','LOC-1'],
                ['ESC-B','PAY','TRUST-H','SELLER','400','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-A','CLOSE-A','ESC-A','PAY','TRUST-H','SELLER','200','20260613101000','CLOSE','LOC-1'],
                ['ACT-B','CLOSE-B','ESC-B','PAY','TRUST-H','SELLER','400','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-H','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-A','ESC-A','TRUST-H','200','SELLER','CLOSED'],
                ['CLOSE-B','ESC-B','TRUST-H','400','SELLER','OPEN'],
            ],
            [['TRUST-H','500']],
            [['TRUST-H','1','400']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-A']['status'] == 'HELD'
        assert groups['CLOSE-A']['reason'] == 'PACKAGE_NOT_OPEN'
        assert groups['CLOSE-B']['status'] == 'CLEARED'
        assert rows(BALANCE_AFTER) == [{'trust_id': 'TRUST-H', 'balance': '100'}]

    def test_control_total_amount_mismatch_holds_groups(self):
        """Operator control totals must reconcile on both group count and total amount."""
        write_inputs(
            [
                ['ESC-X','PAY-S','TRUST-G','SELLER','100','20260613100000','HELD','LOC-1'],
                ['ESC-Y','PAY-S','TRUST-G','SELLER','200','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-X','CLOSE-X','ESC-X','PAY-S','TRUST-G','SELLER','100','20260613101000','CLOSE','LOC-1'],
                ['ACT-Y','CLOSE-Y','ESC-Y','PAY-S','TRUST-G','SELLER','200','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-G','20260613095900','20260613103000','OPEN']],
            [['CLOSE-X','ESC-X','TRUST-G','100','SELLER','OPEN'], ['CLOSE-Y','ESC-Y','TRUST-G','200','SELLER','OPEN']],
            [['TRUST-G','1000']],
            [['TRUST-G','2','999']],
        )
        run_ok()
        assert {r['status'] for r in rows(GROUPS)} == {'HELD'}
        assert {r['reason'] for r in rows(GROUPS)} == {'CONTROL_TOTAL_MISMATCH'}

    def test_trust_funding_uses_closing_package_input_order(self):
        """Funding must follow closing_packages.csv row order, not closing_id alphabetical order."""
        write_inputs(
            [
                ['ESC-B','PAY-S','TRUST-O','SELLER','300','20260613100000','HELD','LOC-1'],
                ['ESC-A','PAY-S','TRUST-O','SELLER','200','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-B','CLOSE-B','ESC-B','PAY-S','TRUST-O','SELLER','300','20260613101000','CLOSE','LOC-1'],
                ['ACT-A','CLOSE-A','ESC-A','PAY-S','TRUST-O','SELLER','200','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-O','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-B','ESC-B','TRUST-O','300','SELLER','OPEN'],
                ['CLOSE-A','ESC-A','TRUST-O','200','SELLER','OPEN'],
            ],
            [['TRUST-O','400']],
            [['TRUST-O','2','500']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-B']['status'] == 'CLEARED'
        assert groups['CLOSE-A']['status'] == 'HELD'
        assert groups['CLOSE-A']['reason'] == 'INSUFFICIENT_FUNDS'
        assert rows(BALANCE_AFTER) == [{'trust_id': 'TRUST-O', 'balance': '100'}]

    def test_location_mismatch_still_blocks_clearing_with_funding(self):
        """Location mismatches must remain UNMATCHED and keep the package HELD under funding rules."""
        write_inputs(
            [
                ['ESC-LOC','PAY','TRUST-L','SELLER','120','20260613100000','HELD','LOC-1'],
            ],
            [
                ['ACT-LOC','CLOSE-LOC','ESC-LOC','PAY','TRUST-L','SELLER','120','20260613101000','CLOSE','LOC-2'],
            ],
            [['TRUST-L','20260613095900','20260613103000','OPEN']],
            [['CLOSE-LOC','ESC-LOC','TRUST-L','120','SELLER','OPEN']],
            [['TRUST-L','500']],
            [['TRUST-L','1','120']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-LOC']['status'] == 'HELD'
        assert groups['CLOSE-LOC']['reason'] == 'UNMATCHED_ACTION'
        assert rows(BALANCE_AFTER) == [{'trust_id': 'TRUST-L', 'balance': '500'}]

    def test_control_total_mismatch_takes_precedence_over_insufficient_funds(self):
        """Control-total reconciliation must run before funding and override insufficient-funds holds."""
        write_inputs(
            [
                ['ESC-A','PAY','TRUST-P','SELLER','200','20260613100000','HELD','LOC-1'],
                ['ESC-B','PAY','TRUST-P','SELLER','150','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-A','CLOSE-A','ESC-A','PAY','TRUST-P','SELLER','200','20260613101000','CLOSE','LOC-1'],
                ['ACT-B','CLOSE-B','ESC-B','PAY','TRUST-P','SELLER','150','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-P','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-A','ESC-A','TRUST-P','200','SELLER','OPEN'],
                ['CLOSE-B','ESC-B','TRUST-P','150','SELLER','OPEN'],
            ],
            [['TRUST-P','50']],
            [['TRUST-P','3','999']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-A']['status'] == 'HELD'
        assert groups['CLOSE-B']['status'] == 'HELD'
        assert groups['CLOSE-A']['reason'] == 'CONTROL_TOTAL_MISMATCH'
        assert groups['CLOSE-B']['reason'] == 'CONTROL_TOTAL_MISMATCH'
        assert rows(BALANCE_AFTER) == [{'trust_id': 'TRUST-P', 'balance': '50'}]
