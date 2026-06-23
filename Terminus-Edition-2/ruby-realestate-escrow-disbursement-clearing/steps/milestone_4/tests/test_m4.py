
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


class TestMilestone4:
    def test_abend_restart_commits_each_cleared_group_exactly_once(self):
        """A restart after ABEND should continue pending groups without duplicating committed ones."""
        write_inputs(
            [
                ['ESC-1','PAY','TRUST-R','SELLER','100','20260613100000','HELD','LOC-1'],
                ['ESC-2','PAY','TRUST-R','SELLER','200','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-1','CLOSE-1','ESC-1','PAY','TRUST-R','SELLER','100','20260613101000','CLOSE','LOC-1'],
                ['ACT-2','CLOSE-2','ESC-2','PAY','TRUST-R','SELLER','200','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-R','20260613095900','20260613103000','OPEN']],
            [['CLOSE-1','ESC-1','TRUST-R','100','SELLER','OPEN'], ['CLOSE-2','ESC-2','TRUST-R','200','SELLER','OPEN']],
            [['TRUST-R','1000']],
            [['TRUST-R','2','300']],
        )
        first = run_fail({'ABEND_AFTER_GROUPS': '1'})
        assert first.returncode != 0
        assert rows(COMMITS) == [{'commit_id': 'COMMIT-CLOSE-1', 'closing_id': 'CLOSE-1', 'trust_id': 'TRUST-R', 'amount': '100', 'committed_at': '20260613000000'}]
        checkpoint = CHECKPOINT.read_text()
        assert set(checkpoint.strip().splitlines()) == {
            'last_committed_closing_id=CLOSE-1',
            'committed_count=1',
            'status=ABENDED',
        }
        bal_first = rows(BALANCE_AFTER)
        run_ok()
        commits = rows(COMMITS)
        assert commits == [
            {'commit_id': 'COMMIT-CLOSE-1', 'closing_id': 'CLOSE-1', 'trust_id': 'TRUST-R', 'amount': '100', 'committed_at': '20260613000000'},
            {'commit_id': 'COMMIT-CLOSE-2', 'closing_id': 'CLOSE-2', 'trust_id': 'TRUST-R', 'amount': '200', 'committed_at': '20260613000000'},
        ]
        checkpoint = CHECKPOINT.read_text()
        assert set(checkpoint.strip().splitlines()) == {
            'last_committed_closing_id=CLOSE-2',
            'committed_count=2',
            'status=COMPLETE',
        }
        run_ok()
        assert [r['closing_id'] for r in rows(COMMITS)] == ['CLOSE-1', 'CLOSE-2']
        assert rows(BALANCE_AFTER) == bal_first

    def test_abend_limit_two_commits_exactly_two_of_three_groups(self):
        """ABEND_AFTER_GROUPS must honor N rather than always stopping after one commit."""
        write_inputs(
            [
                ['ESC-A','PAY','TRUST-N','SELLER','100','20260613100000','HELD','LOC-1'],
                ['ESC-B','PAY','TRUST-N','SELLER','200','20260613100100','HELD','LOC-2'],
                ['ESC-C','PAY','TRUST-N','SELLER','300','20260613100200','HELD','LOC-3'],
            ],
            [
                ['ACT-A','CLOSE-A','ESC-A','PAY','TRUST-N','SELLER','100','20260613101000','CLOSE','LOC-1'],
                ['ACT-B','CLOSE-B','ESC-B','PAY','TRUST-N','SELLER','200','20260613101100','CLOSE','LOC-2'],
                ['ACT-C','CLOSE-C','ESC-C','PAY','TRUST-N','SELLER','300','20260613101200','CLOSE','LOC-3'],
            ],
            [['TRUST-N','20260613095900','20260613103000','OPEN']],
            [
                ['CLOSE-A','ESC-A','TRUST-N','100','SELLER','OPEN'],
                ['CLOSE-B','ESC-B','TRUST-N','200','SELLER','OPEN'],
                ['CLOSE-C','ESC-C','TRUST-N','300','SELLER','OPEN'],
            ],
            [['TRUST-N','1000']],
            [['TRUST-N','3','600']],
        )
        first = run_fail({'ABEND_AFTER_GROUPS': '2'})
        assert first.returncode != 0
        assert [r['closing_id'] for r in rows(COMMITS)] == ['CLOSE-A', 'CLOSE-B']
        assert rows(BALANCE_AFTER) == [{'trust_id': 'TRUST-N', 'balance': '400'}]
        assert set(CHECKPOINT.read_text().strip().splitlines()) == {
            'last_committed_closing_id=CLOSE-B',
            'committed_count=2',
            'status=ABENDED',
        }

        run_ok()
        assert [r['closing_id'] for r in rows(COMMITS)] == ['CLOSE-A', 'CLOSE-B', 'CLOSE-C']

    def test_held_groups_are_never_committed_across_repeated_reruns(self):
        """Held groups should remain out of the commit ledger even when a completed batch is rerun."""
        write_inputs(
            [
                ['ESC-OK','PAY','TRUST-S','SELLER','90','20260613100000','HELD','LOC-1'],
                ['ESC-HOLD','PAY','TRUST-S','SELLER','500','20260613100100','HELD','LOC-2'],
            ],
            [
                ['ACT-OK','CLOSE-OK','ESC-OK','PAY','TRUST-S','SELLER','90','20260613101000','CLOSE','LOC-1'],
                ['ACT-HOLD','CLOSE-HOLD','ESC-HOLD','PAY','TRUST-S','SELLER','500','20260613101100','CLOSE','LOC-2'],
            ],
            [['TRUST-S','20260613095900','20260613103000','OPEN']],
            [['CLOSE-OK','ESC-OK','TRUST-S','90','SELLER','OPEN'], ['CLOSE-HOLD','ESC-HOLD','TRUST-S','500','SELLER','OPEN']],
            [['TRUST-S','100']],
            [['TRUST-S','2','590']],
        )
        run_ok()
        run_ok()
        assert [r['closing_id'] for r in rows(COMMITS)] == ['CLOSE-OK']
        bal_first = rows(BALANCE_AFTER)
        run_ok()
        assert rows(BALANCE_AFTER) == bal_first
        groups = {r['closing_id']: r for r in rows(GROUPS)}
        assert groups['CLOSE-HOLD']['status'] == 'HELD'
        assert groups['CLOSE-HOLD']['reason'] == 'INSUFFICIENT_FUNDS'
