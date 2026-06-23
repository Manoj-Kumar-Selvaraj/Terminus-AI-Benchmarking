
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

class TestMilestone3:
    """Payment rails, bank verification, and control totals must agree."""

    def test_high_value_eft_waits_for_bank_verification(self):
        """Unverified high-value EFT emits a verification message and no EFT queue row."""
        reset_out()
        write_base_config(verify=75000)
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231'], ['POL-B','MEM-B','ACTIVE','CATA','20260101','20261231'], ['POL-C','MEM-C','ACTIVE','CATA','20260101','20261231'], ['POL-D','MEM-D','ACTIVE','CATA','20260101','20261231'], ['POL-E','MEM-E','ACTIVE','CATA','20260101','20261231'], ['POL-F','MEM-F','ACTIVE','CATA','20260101','20261231'], ['POL-G','MEM-G','ACTIVE','CATA','20260101','20261231'], ['POL-H','MEM-H','ACTIVE','CATA','20260101','20261231']
        ])
        write_psv(BANK_RESPONSES, ['claim_id','event_id','bank_account','status','verified_ts'], [
            ['CLM-VERIFIED','EVT-VERIFIED','BA-2',' approved ','20260613090000']
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-VERIFY','EVT-VERIFY','POL-A','MEM-A','FAC-TRUST','DX-CATA','90000','EFT','BA-1','ID1','APPROVED','AUTH1','B3','20260613080000'],
            ['CLM-VERIFIED','EVT-VERIFIED','POL-B','MEM-B','FAC-TRUST','DX-CATA','91000','EFT','BA-2','ID2','APPROVED','AUTH2','B3','20260613080100'],
            ['CLM-LOW','EVT-LOW','POL-C','MEM-C','FAC-TRUST','DX-CATA','20000','EFT','BA-3','ID3','APPROVED','AUTH3','B3','20260613080200'],
            ['CLM-ID','EVT-ID','POL-D','MEM-D','FAC-TRUST','DX-CATA','10000','CHECK','','CONFLICT','APPROVED','AUTH4','B3','20260613080300'],
            ['CLM-MIS','EVT-MIS','POL-G','MEM-G','FAC-TRUST','DX-CATA','11000','CHECK','','MISMATCH','APPROVED','AUTH8','B3','20260613080700'],
            ['CLM-DUP','EVT-DUP','POL-H','MEM-H','FAC-TRUST','DX-CATA','12000','CHECK','','DUPLICATE_IDENTITY','APPROVED','AUTH9','B3','20260613080800'],
            ['CLM-COLLIDE-A','EVT-COLLIDE-A','POL-E','MEM-E','FAC-TRUST','DX-CATA','15000','CHECK','','SHARED-ID','APPROVED','AUTH5','B3','20260613080400'],
            ['CLM-COLLIDE-B','EVT-COLLIDE-B','POL-F','MEM-F','FAC-TRUST','DX-CATA','16000','CHECK','','SHARED-ID','APPROVED','AUTH6','B3','20260613080500'],
            ['CLM-REJECT','EVT-REJECT','POL-Z','MEM-Z','FAC-TRUST','DX-CATA','12000','CHECK','','ID7','APPROVED','AUTH7','B3','20260613080600'],
        ])
        run_batch()
        verify = {r['claim_id']: r for r in read_psv(VERIFY)}
        efts = {r['claim_id']: r for r in read_psv(EFT)}
        reviews = {r['claim_id']: r['reason_code'] for r in read_psv(REVIEWS)}
        assert verify['CLM-VERIFY']['reason_code'] == 'BANK_VERIFY_REQUIRED'
        assert 'CLM-VERIFY' not in efts
        assert reviews['CLM-VERIFY'] == 'BANK_VERIFY_REQUIRED'
        assert {'CLM-VERIFIED', 'CLM-LOW'} <= set(efts)
        assert reviews['CLM-ID'] == 'IDENTITY_CONFLICT'
        assert reviews['CLM-MIS'] == 'IDENTITY_CONFLICT'
        assert reviews['CLM-DUP'] == 'IDENTITY_CONFLICT'
        assert reviews['CLM-COLLIDE-A'] == 'IDENTITY_CONFLICT'
        assert reviews['CLM-COLLIDE-B'] == 'IDENTITY_CONFLICT'
        ledger_ids = {r['claim_id'] for r in read_psv(LEDGER)}
        assert ledger_ids == {'CLM-VERIFIED', 'CLM-LOW'}

    def test_control_totals_reconcile_side_effect_outputs(self):
        """Control totals must report queued payment, review, reject, and ledger counts."""
        self.test_high_value_eft_waits_for_bank_verification()
        control = {r['metric']: r for r in read_psv(CONTROL)}
        required_metrics = {'payment_queued', 'manual_review', 'rejected', 'check_queue', 'eft_queue', 'bank_verify', 'committed_ledger'}
        assert required_metrics <= set(control)
        assert control['payment_queued']['count'] == '2'
        assert control['manual_review']['count'] == '6'
        assert control['rejected']['count'] == '1'
        assert control['rejected']['amount_cents'] == '12000'
        assert control['check_queue']['count'] == '0'
        assert control['bank_verify']['count'] == '1'
        assert control['committed_ledger']['count'] == '2'
        assert control['eft_queue']['amount_cents'] == '111000'
        reviews_data = read_psv(REVIEWS)
        review_sum = sum(int(r['amount_cents']) for r in reviews_data)
        assert int(control['manual_review']['amount_cents']) == review_sum
        ledger_data = read_psv(LEDGER)
        ledger_sum = sum(int(r['amount_cents']) for r in ledger_data)
        assert int(control['committed_ledger']['amount_cents']) == ledger_sum
        rejects = read_psv(REJECTS)
        assert len(rejects) == int(control['rejected']['count'])
        assert sum(int(r['amount_cents']) for r in read_psv(DECISIONS) if r['decision'] == 'REJECT') == int(control['rejected']['amount_cents'])
