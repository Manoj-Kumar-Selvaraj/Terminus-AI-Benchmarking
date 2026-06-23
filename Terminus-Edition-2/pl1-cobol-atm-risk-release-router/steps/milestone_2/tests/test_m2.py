
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

class TestMilestone2:
    """Matched releases must update the persistent card exposure ledger exactly once."""

    def test_card_exposure_updates_only_for_absorbable_releases(self):
        """A missing or insufficient card ledger must not be silently released."""
        write_rules()
        write_risk()
        write_base_files(
            [['H1','CARD1','TERM-A','CASH','30000','20260613100000','LOCKED','N'], ['H2','CARD2','TERM-A','CASH','25000','20260613100100','LOCKED','N'], ['H3','CARD3','TERM-A','CASH','12000','20260613100200','LOCKED','N']],
            [['R1','H1','CARD1','TERM-A','CASH','30000','20260613110000','OKAY','N'], ['R2','H2','CARD2','TERM-A','CASH','25000','20260613110100','OKAY','N'], ['R3','H3','CARD3','TERM-A','CASH','12000','20260613110200','OKAY','N']],
            exposure=[['CARD1','20260613','50000','10000','1','NONE'], ['CARD2','20260613','10000','0','0','NONE']]
        )
        run_batch()
        assert {r['release_id']: r['status'] for r in read_csv(REPORT)} == {'R1':'MATCHED','R2':'UNMATCHED','R3':'UNMATCHED'}
        exposure = {r['card_id']: r for r in read_psv(EXPOSURE_OUT)}
        assert exposure['CARD1']['active_hold_cents'] == '20000'
        assert exposure['CARD1']['released_today_cents'] == '40000'
        assert exposure['CARD1']['release_count_today'] == '2'
        assert exposure['CARD2']['active_hold_cents'] == '10000'

    def test_channel_aliases_still_feed_exposure_updates(self):
        """The PL/I alias deck is still honored before card exposure is updated."""
        write_rules(aliases=('ATM=>CASH','POS=>MERCHANT','WEB=>ONLINE'))
        write_base_files(
            [['H4','CARD4','TERM-A','CASH','15000','20260613100000','LOCKED','N']],
            [['R4','H4','CARD4','TERM-A','ATM','15000','20260613110000','OKAY','N']],
            exposure=[['CARD4','20260613','20000','0','0','NONE']]
        )
        run_batch()
        assert read_csv(REPORT)[0]['status'] == 'MATCHED'
        assert read_psv(EXPOSURE_OUT)[0]['active_hold_cents'] == '5000'
