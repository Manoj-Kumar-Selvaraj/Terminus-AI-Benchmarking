
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


GROUP_HEADER = [
    'closing_id', 'escrow_id', 'trust_id', 'required_kinds', 'matched_kinds',
    'matched_amount', 'expected_amount', 'status', 'reason',
]


def assert_group_header():
    with GROUPS.open(newline='') as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == GROUP_HEADER


class TestMilestone2:
    def test_aliases_and_complete_closing_package_clear_as_group(self):
        """Alias-matched SELLER/BROKER/TAX rows should clear only when the whole package is complete."""
        write_inputs(
            [
                ['ESC-100','PAY-S','TRUST-C','SELLER','700','20260613100000','HELD','LOC-1'],
                ['ESC-100','PAY-B','TRUST-C','BROKER','200','20260613100100','HELD','LOC-1'],
                ['ESC-100','PAY-T','TRUST-C','TAX','100','20260613100200','HELD','LOC-1'],
                ['ESC-200','PAY-S','TRUST-C','SELLER','500','20260613100300','HELD','LOC-2'],
                ['ESC-200','PAY-B','TRUST-C','BROKER','75','20260613100400','HELD','LOC-2'],
            ],
            [
                ['ACT-100-S','CLOSE-100','ESC-100','PAY-S','TRUST-C','slr','700','20260613101000','CLOSE','LOC-1'],
                ['ACT-100-B','CLOSE-100','ESC-100','PAY-B','TRUST-C','Brk','200','20260613101100','CLOSE','LOC-1'],
                ['ACT-100-T','CLOSE-100','ESC-100','PAY-T','TRUST-C','TaxAuth','100','20260613101200','CLOSE','LOC-1'],
                ['ACT-200-S','CLOSE-200','ESC-200','PAY-S','TRUST-C','SLR','500','20260613101300','CLOSE','LOC-2'],
                ['ACT-200-B','CLOSE-200','ESC-200','PAY-B','TRUST-C','BRK','75','20260613101400','CLOSE','LOC-2'],
            ],
            [['TRUST-C','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-100','ESC-100','TRUST-C','1000','SELLER|BROKER|TAX','OPEN'],
                ['CLOSE-200','ESC-200','TRUST-C','600','SELLER|BROKER|TAX','OPEN'],
            ],
            [['TRUST-C','5000']],
            [['TRUST-C','1','1000']],
        )
        run_ok()
        assert_group_header()
        report = rows(REPORT)
        assert [r['status'] for r in report] == ['MATCHED','MATCHED','MATCHED','MATCHED','MATCHED']
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-100']['status'] == 'CLEARED'
        assert groups['CLOSE-100']['reason'] == 'OK'
        assert groups['CLOSE-100']['matched_amount'] == '1000'
        assert groups['CLOSE-100']['expected_amount'] == '1000'
        assert set(groups['CLOSE-100']['required_kinds'].split('|')) == {'SELLER', 'BROKER', 'TAX'}
        assert set(groups['CLOSE-100']['matched_kinds'].split('|')) == {'SELLER', 'BROKER', 'TAX'}
        assert groups['CLOSE-200']['status'] == 'HELD'
        assert groups['CLOSE-200']['reason'] == 'MISSING_KIND:TAX'
        assert groups['CLOSE-200']['expected_amount'] == '600'
        assert set(groups['CLOSE-200']['matched_kinds'].split('|')) == {'SELLER', 'BROKER'}

    def test_unmatched_row_or_total_mismatch_holds_entire_package(self):
        """One bad row or package total mismatch must prevent package clearing."""
        write_inputs(
            [
                ['ESC-300','PAY-S','TRUST-D','SELLER','80','20260613100000','HELD','LOC-1'],
                ['ESC-300','PAY-B','TRUST-D','BROKER','20','20260613100100','HELD','LOC-1'],
                ['ESC-400','PAY-S','TRUST-D','SELLER','60','20260613100200','HELD','LOC-2'],
            ],
            [
                ['ACT-300-S','CLOSE-300','ESC-300','PAY-S','TRUST-D','SELLER','80','20260613101000','CLOSE','LOC-1'],
                ['ACT-300-B','CLOSE-300','ESC-300','PAY-BAD','TRUST-D','BROKER','20','20260613101100','CLOSE','LOC-1'],
                ['ACT-400-S','CLOSE-400','ESC-400','PAY-S','TRUST-D','SELLER','60','20260613101200','CLOSE','LOC-2'],
            ],
            [['TRUST-D','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-300','ESC-300','TRUST-D','100','SELLER|BROKER','OPEN'],
                ['CLOSE-400','ESC-400','TRUST-D','75','SELLER','OPEN'],
            ],
            [['TRUST-D','5000']],
            [['TRUST-D','0','0']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-300']['status'] == 'HELD'
        assert groups['CLOSE-300']['reason'] == 'UNMATCHED_ACTION'
        assert groups['CLOSE-300']['expected_amount'] == '100'
        assert groups['CLOSE-300']['matched_kinds'] == 'SELLER'
        assert groups['CLOSE-400']['status'] == 'HELD'
        assert groups['CLOSE-400']['reason'] == 'TOTAL_MISMATCH'
        assert groups['CLOSE-400']['expected_amount'] == '75'
        assert groups['CLOSE-400']['matched_kinds'] == 'SELLER'

    def test_first_missing_kind_follows_required_kinds_order(self):
        """When multiple kinds are absent, report the first missing kind from required_kinds order."""
        write_inputs(
            [
                ['ESC-500','PAY-S','TRUST-M','SELLER','100','20260613100000','HELD','LOC-1'],
            ],
            [
                ['ACT-500-S','CLOSE-500','ESC-500','PAY-S','TRUST-M','SELLER','100','20260613101000','CLOSE','LOC-1'],
            ],
            [['TRUST-M','20260613095900','20260613103000','OPEN']],
            [['CLOSE-500','ESC-500','TRUST-M','100','SELLER|BROKER|TAX','OPEN']],
            [['TRUST-M','5000']],
            [['TRUST-M','0','0']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-500']['status'] == 'HELD'
        assert groups['CLOSE-500']['reason'] == 'MISSING_KIND:BROKER'
        assert groups['CLOSE-500']['expected_amount'] == '100'
        assert groups['CLOSE-500']['matched_kinds'] == 'SELLER'

    def test_closed_package_is_held_even_when_rows_match(self):
        """Packages with package_state CLOSED must stay HELD with PACKAGE_NOT_OPEN."""
        write_inputs(
            [
                ['ESC-X','PAY','TRUST-X','SELLER','100','20260613100000','HELD','LOC-1'],
            ],
            [
                ['ACT-X','CLOSE-X','ESC-X','PAY','TRUST-X','SELLER','100','20260613101000','CLOSE','LOC-1'],
            ],
            [['TRUST-X','20260613095900','20260613103000','OPEN']],
            [['CLOSE-X','ESC-X','TRUST-X','100','SELLER','CLOSED']],
            [['TRUST-X','5000']],
            [['TRUST-X','0','0']],
        )
        run_ok()
        assert_group_header()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-X']['status'] == 'HELD'
        assert groups['CLOSE-X']['reason'] == 'PACKAGE_NOT_OPEN'
        assert groups['CLOSE-X']['expected_amount'] == '100'

    def test_location_mismatch_prevents_package_clearing(self):
        """A single location mismatch must keep the closing package HELD."""
        write_inputs(
            [
                ['ESC-LOC','PAY','TRUST-L','SELLER','90','20260613100000','HELD','LOC-1'],
            ],
            [
                ['ACT-LOC','CLOSE-LOC','ESC-LOC','PAY','TRUST-L','SELLER','90','20260613101000','CLOSE','LOC-2'],
            ],
            [['TRUST-L','20260613095900','20260613103000','OPEN']],
            [['CLOSE-LOC','ESC-LOC','TRUST-L','90','SELLER','OPEN']],
            [['TRUST-L','5000']],
            [['TRUST-L','0','0']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-LOC']['status'] == 'HELD'
        assert groups['CLOSE-LOC']['reason'] == 'UNMATCHED_ACTION'
        assert groups['CLOSE-LOC']['expected_amount'] == '90'
        assert groups['CLOSE-LOC']['matched_kinds'] == ''

    def test_no_disbursement_rows_holds_package_with_no_matched_rows(self):
        """A closing package with no disbursement actions must stay HELD with NO_MATCHED_ROWS."""
        write_inputs(
            [
                ['ESC-NM','PAY','TRUST-N','SELLER','100','20260613100000','HELD','LOC-1'],
            ],
            [],
            [['TRUST-N','20260613095900','20260613103000','OPEN']],
            [['CLOSE-NM','ESC-NM','TRUST-N','100','SELLER','OPEN']],
            [['TRUST-N','5000']],
            [['TRUST-N','0','0']],
        )
        run_ok()
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-NM']['status'] == 'HELD'
        assert groups['CLOSE-NM']['reason'] == 'NO_MATCHED_ROWS'
        assert groups['CLOSE-NM']['expected_amount'] == '100'
        assert groups['CLOSE-NM']['matched_kinds'] == ''
