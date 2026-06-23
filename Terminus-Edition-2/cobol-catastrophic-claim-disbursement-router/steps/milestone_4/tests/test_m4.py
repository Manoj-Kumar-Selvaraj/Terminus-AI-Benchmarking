
import csv
import os
import subprocess
from pathlib import Path

APP = Path('/app')
DATA = APP/'data'
CONFIG = APP/'config'
OUT = APP/'out'
CLAIMS = DATA/'claims.psv'
POLICIES = DATA/'policies.psv'
DIAG = CONFIG/'diagnosis_policy.psv'
FACILITIES = CONFIG/'facility_trust.psv'
POLICY_DECK = CONFIG/'payment_policy.pli'
REJECT_PRECEDENCE = CONFIG/'reject_precedence.psv'
REVIEW_PRECEDENCE = CONFIG/'review_reason_precedence.psv'
BANK_RESPONSES = DATA/'bank_verification_responses.psv'
PRIOR_LEDGER = DATA/'prior_disbursement_ledger.psv'
DECISIONS = OUT/'payment_decision_report.psv'
REJECTS = OUT/'reject_ledger.psv'
REVIEWS = OUT/'manual_review_queue.psv'
CHECKS = OUT/'check_queue.psv'
EFT = OUT/'eft_queue.psv'
VERIFY = OUT/'bank_verify_messages.psv'
LEDGER = OUT/'payment_ledger.psv'
CONTROL = OUT/'control_totals.psv'
CHECKPOINT = OUT/'restart_checkpoint.txt'

def write_psv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as h:
        w = csv.writer(h, delimiter='|', lineterminator='\n')
        w.writerow(header)
        w.writerows(rows)

def read_psv(path):
    if not path.exists():
        return []
    with path.open(newline='') as h:
        return list(csv.DictReader(h, delimiter='|'))

def reset_out():
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob('*'):
        p.unlink()

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

def write_base_config(expedited=50000, verify=75000, manual=125000):
    write_psv(DIAG, ['diagnosis_code','catastrophic','requires_auth','expedited_allowed'], [
        ['DX-CATA','Y','Y','Y'], ['DX-EMERG','Y','N','Y'], ['DX-CHRONIC','Y','N','N'], ['DX-ROUTINE','N','N','N']
    ])
    write_psv(FACILITIES, ['facility_id','trust_tier','sanctioned','emergency_override'], [
        ['FAC-TRUST','TRUSTED','N','N'], ['FAC-STD','STANDARD','N','N'], ['FAC-ER','STANDARD','N','Y'], ['FAC-BLOCK','UNTRUSTED','Y','N'], ['FAC-UNTRUST','UNTRUSTED','N','N']
    ])
    POLICY_DECK.write_text('\n'.join([
        f'DCL EXPEDITED_CHECK_LIMIT_CENTS FIXED DEC(12) INIT({expedited});',
        f'DCL EFT_BANK_VERIFY_CENTS FIXED DEC(12) INIT({verify});',
        f'DCL MANUAL_REVIEW_LIMIT_CENTS FIXED DEC(12) INIT({manual});',
        "DCL BUSINESS_DATE CHAR(8) INIT('20260613');",
    ]) + '\n')
    write_psv(REJECT_PRECEDENCE, ['rank','reason_code'], [
        ['1','DUPLICATE_EVENT'], ['2','POLICY_NOT_FOUND'], ['3','POLICY_INACTIVE'], ['4','MEMBER_MISMATCH'], ['5','ADJUDICATION_NOT_APPROVED'], ['6','NON_CATASTROPHIC'], ['7','AUTH_REQUIRED'], ['8','AMOUNT_INVALID']
    ])
    write_psv(REVIEW_PRECEDENCE, ['rank','reason_code'], [
        ['1','IDENTITY_CONFLICT'], ['2','FACILITY_SANCTIONED'], ['3','FACILITY_NOT_TRUSTED'], ['4','BANK_VERIFY_REQUIRED'], ['5','MANUAL_LIMIT_EXCEEDED']
    ])
    write_psv(PRIOR_LEDGER, ['instruction_id','claim_id','event_id','rail','amount_cents','status'], [])
    write_psv(BANK_RESPONSES, ['claim_id','event_id','bank_account','status','verified_ts'], [])

class TestMilestone4:
    """ABEND restart must not duplicate committed disbursement side effects."""

    def write_restart_fixture(self):
        reset_out()
        write_base_config(verify=75000)
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231'], ['POL-B','MEM-B','ACTIVE','CATA','20260101','20261231'], ['POL-C','MEM-C','ACTIVE','CATA','20260101','20261231'], ['POL-D','MEM-D','ACTIVE','CATA','20260101','20261231']
        ])
        write_psv(BANK_RESPONSES, ['claim_id','event_id','bank_account','status','verified_ts'], [
            ['CLM-EFT','EVT-EFT','BA-1','APPROVED','20260613090000']
        ])
        write_psv(PRIOR_LEDGER, ['instruction_id','claim_id','event_id','rail','amount_cents','status'], [
            ['PAY-CLM-PRIOR-EVT-PRIOR','CLM-PRIOR','EVT-PRIOR','CHECK','15000','COMMITTED']
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-CHK','EVT-CHK','POL-A','MEM-A','FAC-TRUST','DX-CATA','20000','CHECK','','ID1','APPROVED','AUTH1','B4','20260613080000'],
            ['CLM-EFT','EVT-EFT','POL-B','MEM-B','FAC-TRUST','DX-CATA','80000','EFT','BA-1','ID2','APPROVED','AUTH2','B4','20260613080100'],
            ['CLM-REVIEW','EVT-REVIEW','POL-C','MEM-C','FAC-BLOCK','DX-CATA','25000','CHECK','','ID3','APPROVED','AUTH3','B4','20260613080200'],
            ['CLM-PRIOR','EVT-PRIOR','POL-D','MEM-D','FAC-TRUST','DX-CATA','15000','CHECK','','ID4','APPROVED','AUTH4','B4','20260613080300'],
        ])

    def test_restart_resumes_after_abend_without_duplicate_queues(self):
        """A rerun after deterministic ABEND must finish pending rows only once."""
        self.write_restart_fixture()
        run_batch(env={'ABEND_AFTER_COMMITS': '1'}, expect_ok=False)
        ledger_after_abend = read_psv(LEDGER)
        assert [r['instruction_id'] for r in ledger_after_abend if r['claim_id'] != 'CLM-PRIOR'] == ['PAY-CLM-CHK-EVT-CHK']
        assert 'PAY-CLM-CHK-EVT-CHK' in CHECKPOINT.read_text()
        run_batch()
        ledger = [r for r in read_psv(LEDGER) if r['claim_id'] != 'CLM-PRIOR']
        assert [r['instruction_id'] for r in ledger] == ['PAY-CLM-CHK-EVT-CHK', 'PAY-CLM-EFT-EVT-EFT']
        assert [r['instruction_id'] for r in read_psv(CHECKS)] == ['PAY-CLM-CHK-EVT-CHK']
        assert [r['instruction_id'] for r in read_psv(EFT)] == ['PAY-CLM-EFT-EVT-EFT']
        verify_rows = read_psv(VERIFY)
        verify_ids = [r['instruction_id'] for r in verify_rows]
        assert len(verify_ids) == len(set(verify_ids))
        reviews = {r['claim_id']: r['reason_code'] for r in read_psv(REVIEWS)}
        assert reviews == {'CLM-REVIEW': 'FACILITY_SANCTIONED'}
        decisions = {r['claim_id']: r for r in read_psv(DECISIONS)}
        assert decisions['CLM-PRIOR']['decision'] == 'ALREADY_COMMITTED'

    def test_clean_rerun_is_idempotent(self):
        """Repeated clean runs must not append duplicate payment, queue, or review rows."""
        self.write_restart_fixture()
        run_batch()
        first = {
            'ledger': LEDGER.read_text(),
            'checks': CHECKS.read_text(),
            'eft': EFT.read_text(),
            'reviews': REVIEWS.read_text(),
            'verify': VERIFY.read_text(),
            'control': CONTROL.read_text(),
        }
        run_batch()
        assert LEDGER.read_text() == first['ledger']
        assert CHECKS.read_text() == first['checks']
        assert EFT.read_text() == first['eft']
        assert REVIEWS.read_text() == first['reviews']
        assert VERIFY.read_text() == first['verify']
        assert CONTROL.read_text() == first['control']
