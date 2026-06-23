
import csv
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
REPORT = APP / 'out' / 'release_report.csv'
SUMMARY = APP / 'out' / 'release_summary.txt'
EXPOSURE_OUT = APP / 'out' / 'card_exposure_after.psv'
DECISIONS = APP / 'out' / 'risk_release_decisions.psv'
REVIEW_QUEUE = APP / 'out' / 'manual_review_queue.psv'
JOURNAL = APP / 'out' / 'risk_release_journal.psv'
CHECKPOINT = APP / 'out' / 'restart_checkpoint.txt'

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

def write_base_files(holds, releases, exposure=None, trust=None, approvals=None):
    write_psv(HOLDS, ['hold_id','card_id','terminal_id','channel','amount_cents','hold_ts','status','region'], holds)
    write_psv(RELEASES, ['release_id','hold_id','card_id','terminal_id','channel','amount_cents','release_ts','reason','region'], releases)
    write_psv(WINDOWS, ['terminal_id','open_ts','close_ts','state'], [['TERM-A','20260613090000','20260613170000','OPEN'], ['TERM-B','20260613090000','20260613170000','OPEN'], ['TERM-C','20260613090000','20260613170000','OPEN']])
    write_psv(EXPOSURE, ['card_id','business_date','active_hold_cents','released_today_cents','release_count_today','risk_flags'], exposure or [])
    write_psv(TRUST, ['terminal_id','trust_tier','region','max_release_cents','supervisor_above_cents'], trust or [['TERM-A','TRUSTED','N','70000','60000'], ['TERM-B','STANDARD','S','35000','30000'], ['TERM-C','UNTRUSTED','N','0','1']])
    write_psv(APPROVALS, ['release_id','approver_id','approved_ts','status'], approvals or [])
    for p in [REPORT,SUMMARY,EXPOSURE_OUT,DECISIONS,REVIEW_QUEUE,JOURNAL,CHECKPOINT]:
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

class TestMilestone3:
    """Risk thresholds and terminal trust route unsafe releases to manual review."""

    def test_watchlist_blocked_and_limit_releases_route_to_review(self):
        """Review-routed releases must not consume exposure before supervisor approval."""
        write_rules()
        write_risk(amount_limit=60000, count_limit=2, high_value=35000)
        write_base_files(
            [['HA','CARD-A','TERM-A','CASH','20000','20260613100000','LOCKED','N'], ['HB','CARD-B','TERM-A','CASH','10000','20260613100100','LOCKED','N'], ['HC','CARD-C','TERM-C','CASH','5000','20260613100200','LOCKED','N'], ['HD','CARD-D','TERM-B','CASH','45000','20260613100300','LOCKED','S']],
            [['RA','HA','CARD-A','TERM-A','CASH','20000','20260613110000','OKAY','N'], ['RB','HB','CARD-B','TERM-A','CASH','10000','20260613110100','OKAY','N'], ['RC','HC','CARD-C','TERM-C','CASH','5000','20260613110200','OKAY','N'], ['RD','HD','CARD-D','TERM-B','CASH','45000','20260613110300','OKAY','S']],
            exposure=[['CARD-A','20260613','40000','10000','1','NONE'], ['CARD-B','20260613','30000','0','0','WATCHLIST'], ['CARD-C','20260613','20000','0','0','NONE'], ['CARD-D','20260613','90000','10000','1','NONE']]
        )
        run_batch()
        assert {r['release_id']: r['status'] for r in read_csv(REPORT)} == {'RA':'MATCHED','RB':'REVIEW','RC':'REVIEW','RD':'REVIEW'}
        assert {r['release_id']: r['reason_code'] for r in read_psv(REVIEW_QUEUE)} == {'RB':'WATCHLIST_CARD', 'RC':'BLOCKED_TERMINAL', 'RD':'HIGH_VALUE_RELEASE'}
        exposure = {r['card_id']: r for r in read_psv(EXPOSURE_OUT)}
        assert exposure['CARD-A']['active_hold_cents'] == '20000'
        assert exposure['CARD-B']['active_hold_cents'] == '30000'
        assert exposure['CARD-C']['active_hold_cents'] == '20000'
        assert exposure['CARD-D']['active_hold_cents'] == '90000'

    def test_daily_amount_and_count_limits_fail_closed(self):
        """Same-day card limits are enforced after strict eligibility but before exposure mutation."""
        write_rules()
        write_risk(amount_limit=50000, count_limit=2)
        write_base_files(
            [['HL1','CARD-L','TERM-A','CASH','10000','20260613100000','LOCKED','N'], ['HL2','CARD-M','TERM-A','CASH','15000','20260613100100','LOCKED','N']],
            [['RL1','HL1','CARD-L','TERM-A','CASH','10000','20260613110000','OKAY','N'], ['RL2','HL2','CARD-M','TERM-A','CASH','15000','20260613110100','OKAY','N']],
            exposure=[['CARD-L','20260613','30000','20000','2','NONE'], ['CARD-M','20260613','30000','45000','1','NONE']]
        )
        run_batch()
        assert {r['release_id']: r['reason_code'] for r in read_psv(REVIEW_QUEUE)} == {'RL1':'DAILY_COUNT_LIMIT', 'RL2':'DAILY_AMOUNT_LIMIT'}
