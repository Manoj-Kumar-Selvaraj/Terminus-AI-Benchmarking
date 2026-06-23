
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

class TestMilestone1:
    """Eligibility validation must reject before any payment rail side effect."""

    def test_reject_precedence_and_pending_eligible_report(self):
        """Multiple invalid fields must select the configured first reject reason."""
        reset_out()
        write_base_config()
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231'],
            ['POL-B','MEM-B','LAPSED','CATA','20260101','20260331'],
            ['POL-C','MEM-C','ACTIVE','CATA','20260101','20261231'],
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-OK','EVT-OK','POL-A','MEM-A','FAC-TRUST','DX-CATA','25000','CHECK','','ID1','APPROVED','AUTH1','B1','20260613080000'],
            ['CLM-NOPOL','EVT-NOPOL','POL-Z','MEM-Z','FAC-TRUST','DX-CATA','25000','CHECK','','ID2','APPROVED','AUTH2','B1','20260613080100'],
            ['CLM-LAPSED','EVT-LAPSED','POL-B','MEM-X','FAC-TRUST','DX-ROUTINE','25000','CHECK','','ID3','PENDING','','B1','20260613080200'],
            ['CLM-MEMBER','EVT-MEMBER','POL-C','MEM-X','FAC-TRUST','DX-CATA','25000','CHECK','','ID4','APPROVED','AUTH4','B1','20260613080300'],
            ['CLM-AUTH','EVT-AUTH','POL-A','MEM-A','FAC-TRUST','DX-CATA','25000','CHECK','','ID5','APPROVED','','B1','20260613080400'],
            ['CLM-NONCAT','EVT-NONCAT','POL-A','MEM-A','FAC-TRUST','DX-ROUTINE','25000','CHECK','','ID6','APPROVED','AUTH6','B1','20260613080500'],
            ['CLM-ADJ','EVT-ADJ','POL-A','MEM-A','FAC-TRUST','DX-CATA','25000','CHECK','','ID9','PENDING','AUTH9','B1','20260613080600'],
            ['CLM-ZERO','EVT-ZERO','POL-A','MEM-A','FAC-TRUST','DX-CATA','0','CHECK','','ID8','APPROVED','AUTH8','B1','20260613080700'],
        ])
        run_batch()
        decisions = {r['claim_id']: r for r in read_psv(DECISIONS)}
        rejects = {r['claim_id']: r['reason_code'] for r in read_psv(REJECTS)}
        ok = decisions['CLM-OK']
        assert ok['decision'] == 'ELIGIBLE_PENDING_ROUTE'
        assert ok['event_id'] == 'EVT-OK'
        assert ok['policy_id'] == 'POL-A'
        assert ok['amount_cents'] == '25000'
        assert 'CLM-OK' not in rejects
        for cid in ['CLM-NOPOL', 'CLM-LAPSED', 'CLM-MEMBER', 'CLM-ADJ', 'CLM-AUTH', 'CLM-NONCAT', 'CLM-ZERO']:
            assert decisions[cid]['decision'] == 'REJECT'
        assert rejects['CLM-NOPOL'] == 'POLICY_NOT_FOUND'
        assert rejects['CLM-LAPSED'] == 'POLICY_INACTIVE'
        assert rejects['CLM-MEMBER'] == 'MEMBER_MISMATCH'
        assert rejects['CLM-ADJ'] == 'ADJUDICATION_NOT_APPROVED'
        assert rejects['CLM-AUTH'] == 'AUTH_REQUIRED'
        assert rejects['CLM-NONCAT'] == 'NON_CATASTROPHIC'
        assert rejects['CLM-ZERO'] == 'AMOUNT_INVALID'
        assert not CHECKS.exists() or read_psv(CHECKS) == []
        assert not EFT.exists() or read_psv(EFT) == []
        assert not LEDGER.exists() or read_psv(LEDGER) == []

    def test_reject_precedence_is_loaded_from_config_not_hardcoded(self):
        """Changing precedence must change the selected reason for a multi-failure row."""
        reset_out()
        write_base_config()
        write_psv(REJECT_PRECEDENCE, ['rank','reason_code'], [
            ['1','NON_CATASTROPHIC'], ['2','POLICY_INACTIVE'], ['3','MEMBER_MISMATCH'], ['4','ADJUDICATION_NOT_APPROVED'], ['5','AUTH_REQUIRED'], ['6','AMOUNT_INVALID'], ['7','POLICY_NOT_FOUND'], ['8','DUPLICATE_EVENT']
        ])
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [['POL-B','MEM-B','LAPSED','CATA','20260101','20260331']])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-MULTI','EVT-MULTI','POL-B','MEM-X','FAC-TRUST','DX-ROUTINE','25000','CHECK','','ID7','PENDING','','B1','20260613080600']
        ])
        run_batch()
        assert {r['claim_id']: r['reason_code'] for r in read_psv(REJECTS)}['CLM-MULTI'] == 'NON_CATASTROPHIC'
