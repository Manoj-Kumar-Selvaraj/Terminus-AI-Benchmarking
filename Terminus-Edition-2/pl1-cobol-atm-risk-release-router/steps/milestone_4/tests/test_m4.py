
import csv
import json
import os
import subprocess
from pathlib import Path

APP = Path('/app')
RULES = APP / 'src' / 'release_rules.pli'
RISK = APP / 'config' / 'risk_thresholds.pli'
HOLDS = APP / 'data' / 'holds.psv'
RELEASES = APP / 'data' / 'releases.psv'
WINDOWS = APP / 'config' / 'terminal_windows.psv'
EXPOSURE = APP / 'data' / 'card_exposure.psv'
TRUST = APP / 'config' / 'terminal_trust.psv'
APPROVALS = APP / 'data' / 'supervisor_approvals.psv'
CASH = APP / 'data' / 'terminal_cash.psv'
REPORT = APP / 'out' / 'release_report.csv'
SUMMARY = APP / 'out' / 'release_summary.txt'
EXPOSURE_OUT = APP / 'out' / 'card_exposure_after.psv'
CASH_OUT = APP / 'out' / 'terminal_cash_after.psv'
DECISIONS = APP / 'out' / 'risk_release_decisions.psv'
REVIEW_QUEUE = APP / 'out' / 'manual_review_queue.psv'
JOURNAL = APP / 'out' / 'risk_release_journal.psv'
CHECKPOINT = APP / 'out' / 'restart_checkpoint.txt'
MANIFEST = APP / 'out' / 'settlement_manifest.json'

def write_psv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('|'.join(header) + '\n' + ''.join('|'.join(map(str,row)) + '\n' for row in rows))

def read_csv(path):
    with path.open(newline='') as h:
        return list(csv.DictReader(h))

def read_psv(path):
    with path.open(newline='') as h:
        return list(csv.DictReader(h, delimiter='|'))

def read_summary():
    out = {}
    for line in SUMMARY.read_text().splitlines():
        if '=' in line:
            k,v = line.split('=',1)
            out[k] = int(v)
    return out

def write_rules(status='LOCKED', open_state='OPEN', reasons=('OKAY','WATCH','LATE'), aliases=('ATM=>CASH','POS=>MERCHANT','WEB=>ONLINE')):
    RULES.write_text('\n'.join([
        f"DCL ELIGIBLE_HOLD_STATUS CHAR(8) INIT('{status}');",
        f"DCL OPEN_WINDOW_STATUS CHAR(4) INIT('{open_state}');",
        f"DCL REASON_APPROVE CHAR(8) INIT('{reasons[0]}');",
        f"DCL REASON_REVIEW CHAR(8) INIT('{reasons[1]}');",
        f"DCL REASON_EXPIRE CHAR(8) INIT('{reasons[2]}');",
        f"DCL ALIAS_ATM CHAR(16) INIT('{aliases[0]}');",
        f"DCL ALIAS_POS CHAR(16) INIT('{aliases[1]}');",
        f"DCL ALIAS_WEB CHAR(16) INIT('{aliases[2]}');",
    ]) + '\n')

def write_risk(amount_limit=80000, count_limit=3, high_value=40000):
    RISK.write_text('\n'.join([
        "DCL BUSINESS_DATE CHAR(8) INIT('20260613');",
        f"DCL DAILY_RELEASE_LIMIT_CENTS FIXED DEC(12) INIT({amount_limit});",
        f"DCL DAILY_RELEASE_COUNT_LIMIT FIXED BIN(31) INIT({count_limit});",
        f"DCL HIGH_VALUE_RELEASE_CENTS FIXED DEC(12) INIT({high_value});",
        "DCL REVIEW_RISK_FLAG CHAR(16) INIT('WATCHLIST');",
        "DCL TRUSTED_TERMINAL_LIMIT_CENTS FIXED DEC(12) INIT(70000);",
        "DCL STANDARD_TERMINAL_LIMIT_CENTS FIXED DEC(12) INIT(35000);",
        "DCL UNTRUSTED_TERMINAL_LIMIT_CENTS FIXED DEC(12) INIT(0);",
    ]) + '\n')

def write_base_files(holds, releases, exposure=None, trust=None, approvals=None, cash=None):
    write_psv(HOLDS, ['hold_id','card_id','terminal_id','channel','amount_cents','hold_ts','status','region'], holds)
    write_psv(RELEASES, ['release_id','hold_id','card_id','terminal_id','channel','amount_cents','release_ts','reason','region'], releases)
    write_psv(WINDOWS, ['terminal_id','open_ts','close_ts','state'], [['TERM-A','20260613090000','20260613170000','OPEN'], ['TERM-B','20260613090000','20260613170000','OPEN'], ['TERM-C','20260613090000','20260613170000','OPEN']])
    write_psv(EXPOSURE, ['card_id','business_date','active_hold_cents','released_today_cents','release_count_today','risk_flags'], exposure or [])
    write_psv(TRUST, ['terminal_id','trust_tier','region','max_release_cents','supervisor_above_cents'], trust or [['TERM-A','TRUSTED','N','70000','60000'], ['TERM-B','STANDARD','S','35000','30000'], ['TERM-C','UNTRUSTED','N','0','1']])
    write_psv(APPROVALS, ['release_id','approver_id','approved_ts','status'], approvals or [])
    write_psv(CASH, ['terminal_id','business_date','available_cash_cents','dispensed_today_cents','release_count_today','state'], cash or [['TERM-A','20260613','100000','0','0','READY'], ['TERM-B','20260613','100000','0','0','READY'], ['TERM-C','20260613','100000','0','0','READY']])
    for p in [REPORT,SUMMARY,EXPOSURE_OUT,CASH_OUT,DECISIONS,REVIEW_QUEUE,JOURNAL,CHECKPOINT,MANIFEST]:
        p.unlink(missing_ok=True)

def run_batch(env=None, expect_ok=True):
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    result = subprocess.run(['/app/scripts/run_batch.sh'], cwd=APP, env=env_vars, text=True, capture_output=True, timeout=90)
    if expect_ok and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    if not expect_ok and result.returncode == 0:
        raise AssertionError('expected non-zero exit')
    return result

class TestMilestone4:
    """Committed releases and approved reviews must survive ABEND/restart without duplicates."""

    def test_restart_skips_committed_releases_and_commits_approved_reviews_once(self):
        """ABEND after one commit must leave a journal that the rerun resumes from safely."""
        write_rules()
        write_risk(amount_limit=90000, count_limit=5, high_value=30000)
        write_base_files(
            [['H1','CARD1','TERM-A','CASH','20000','20260613100000','LOCKED','N'], ['H2','CARD2','TERM-B','CASH','45000','20260613100100','LOCKED','S'], ['H3','CARD3','TERM-A','CASH','10000','20260613100200','LOCKED','N']],
            [['R1','H1','CARD1','TERM-A','CASH','20000','20260613110000','OKAY','N'], ['REL-APPROVED','H2','CARD2','TERM-B','CASH','45000','20260613110100','OKAY','S'], ['REL-DENIED','H3','CARD3','TERM-A','CASH','10000','20260613110200','OKAY','N']],
            exposure=[['CARD1','20260613','40000','0','0','NONE'], ['CARD2','20260613','80000','0','0','NONE'], ['CARD3','20260613','30000','0','0','WATCHLIST']],
            approvals=[['REL-APPROVED','OPS-17','20260613123000','APPROVED'], ['REL-DENIED','OPS-22','20260613124000','DENIED']]
        )
        run_batch(env={'ABEND_AFTER_COMMITS':'1'}, expect_ok=False)
        assert [r['release_id'] for r in read_psv(JOURNAL)] == ['R1']
        assert 'last_committed_release_id=R1' in CHECKPOINT.read_text()
        run_batch()
        assert [r['release_id'] for r in read_psv(JOURNAL)] == ['R1','REL-APPROVED']
        exposure = {r['card_id']: r for r in read_psv(EXPOSURE_OUT)}
        cash = {r['terminal_id']: r for r in read_psv(CASH_OUT)}
        assert exposure['CARD1']['active_hold_cents'] == '20000'
        assert exposure['CARD2']['active_hold_cents'] == '35000'
        assert exposure['CARD3']['active_hold_cents'] == '30000'
        assert cash['TERM-A']['available_cash_cents'] == '80000'
        assert cash['TERM-A']['dispensed_today_cents'] == '20000'
        assert cash['TERM-B']['available_cash_cents'] == '55000'
        assert cash['TERM-B']['dispensed_today_cents'] == '45000'
        assert {r['release_id']: r['reason_code'] for r in read_psv(REVIEW_QUEUE)} == {'REL-DENIED':'WATCHLIST_CARD'}
        manifest = json.loads(MANIFEST.read_text())
        assert manifest == {
            'schema_version': 1,
            'checkpoint_release_id': 'REL-APPROVED',
            'committed_release_count': 2,
            'committed_amount_cents': 65000,
            'review_release_count': 1,
            'terminal_balances': [
                {'terminal_id':'TERM-A','available_cash_cents':80000,'dispensed_today_cents':20000},
                {'terminal_id':'TERM-B','available_cash_cents':55000,'dispensed_today_cents':45000},
                {'terminal_id':'TERM-C','available_cash_cents':100000,'dispensed_today_cents':0},
            ],
        }

    def test_rerun_is_idempotent_when_all_commits_already_exist(self):
        """A clean rerun must not append duplicate journal rows or double-apply exposure."""
        run_batch()
        assert [r['release_id'] for r in read_psv(JOURNAL)] == ['R1','REL-APPROVED']
        exposure = {r['card_id']: r for r in read_psv(EXPOSURE_OUT)}
        cash = {r['terminal_id']: r for r in read_psv(CASH_OUT)}
        assert exposure['CARD1']['released_today_cents'] == '20000'
        assert exposure['CARD2']['released_today_cents'] == '45000'
        assert cash['TERM-A']['dispensed_today_cents'] == '20000'
        assert cash['TERM-B']['dispensed_today_cents'] == '45000'

    def test_terminal_liquidity_and_stale_approval_fail_closed(self):
        """Cash shortages and approvals predating the release stay in manual review."""
        write_rules()
        write_risk(amount_limit=90000, count_limit=5, high_value=30000)
        write_base_files(
            [['HC1','CARD-C1','TERM-A','CASH','40000','20260613100000','LOCKED','N'], ['HC2','CARD-C2','TERM-B','CASH','35000','20260613100100','LOCKED','S']],
            [['RC1','HC1','CARD-C1','TERM-A','CASH','40000','20260613110000','OKAY','N'], ['RC2','HC2','CARD-C2','TERM-B','CASH','35000','20260613110100','OKAY','S']],
            exposure=[['CARD-C1','20260613','60000','0','0','NONE'], ['CARD-C2','20260613','60000','0','0','NONE']],
            approvals=[['RC2','OPS-OLD','20260613100000','APPROVED']],
            cash=[['TERM-A','20260613','10000','0','0','READY'], ['TERM-B','20260613','90000','0','0','READY']]
        )

        run_batch()

        assert {r['release_id']: r['status'] for r in read_csv(REPORT)} == {'RC1':'REVIEW','RC2':'REVIEW'}
        assert {r['release_id']: r['reason_code'] for r in read_psv(REVIEW_QUEUE)} == {
            'RC1':'TERMINAL_CASH_SHORTAGE',
            'RC2':'HIGH_VALUE_RELEASE',
        }
        cash = {r['terminal_id']: r for r in read_psv(CASH_OUT)}
        assert cash['TERM-A']['available_cash_cents'] == '10000'
        assert cash['TERM-B']['available_cash_cents'] == '90000'
        assert read_psv(JOURNAL) == []
