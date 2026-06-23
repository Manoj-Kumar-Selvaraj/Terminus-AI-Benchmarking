
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

class TestMilestone2:
    """Facility trust must control expedited checks and manual-review routing."""

    def test_trusted_and_emergency_facilities_get_expedited_checks(self):
        """Trusted or emergency override facilities may receive expedited checks within threshold."""
        reset_out()
        write_base_config(expedited=30000)
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231'], ['POL-B','MEM-B','ACTIVE','CATA','20260101','20261231'], ['POL-C','MEM-C','ACTIVE','CATA','20260101','20261231'], ['POL-D','MEM-D','ACTIVE','CATA','20260101','20261231'], ['POL-E','MEM-E','ACTIVE','CATA','20260101','20261231']
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-TRUST','EVT-TRUST','POL-A','MEM-A','FAC-TRUST','DX-CATA','20000','CHECK','','ID1','APPROVED','AUTH1','B2','20260613080000'],
            ['CLM-ER','EVT-ER','POL-B','MEM-B','FAC-ER','DX-EMERG','22000','CHECK','','ID2','APPROVED','','B2','20260613080100'],
            ['CLM-NORM','EVT-NORM','POL-C','MEM-C','FAC-STD','DX-CHRONIC','45000','CHECK','','ID3','APPROVED','','B2','20260613080200'],
            ['CLM-OVER','EVT-OVER','POL-D','MEM-D','FAC-TRUST','DX-CATA','35000','CHECK','','ID4','APPROVED','AUTH4','B2','20260613080300'],
            ['CLM-NOEXP','EVT-NOEXP','POL-E','MEM-E','FAC-TRUST','DX-CHRONIC','20000','CHECK','','ID5','APPROVED','','B2','20260613080400'],
        ])
        run_batch()
        checks = {r['claim_id']: r for r in read_psv(CHECKS)}
        assert checks['CLM-TRUST']['priority'] == 'EXPEDITED'
        assert checks['CLM-ER']['priority'] == 'EXPEDITED'
        assert checks['CLM-NORM']['priority'] == 'NORMAL'
        assert checks['CLM-OVER']['priority'] == 'NORMAL'
        assert checks['CLM-NOEXP']['priority'] == 'NORMAL'
        decisions = {r['claim_id']: r for r in read_psv(DECISIONS)}
        for cid in ['CLM-TRUST', 'CLM-ER', 'CLM-NORM', 'CLM-OVER', 'CLM-NOEXP']:
            assert decisions[cid]['decision'] == 'PAYMENT_QUEUED'

    def test_sanctioned_facility_blocks_even_with_emergency_override(self):
        """Sanctioned facilities must manual-review even when emergency override is set."""
        reset_out()
        write_base_config()
        write_psv(FACILITIES, ['facility_id','trust_tier','sanctioned','emergency_override'], [
            ['FAC-TRUST','TRUSTED','N','N'], ['FAC-STD','STANDARD','N','N'], ['FAC-ER','STANDARD','N','Y'], ['FAC-BLOCK','UNTRUSTED','Y','N'], ['FAC-UNTRUST','UNTRUSTED','N','N'], ['FAC-SANC-ER','UNTRUSTED','Y','Y']
        ])
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231']
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-SANC-ER','EVT-SANC-ER','POL-A','MEM-A','FAC-SANC-ER','DX-EMERG','20000','CHECK','','ID10','APPROVED','','B2','20260613080500'],
        ])
        run_batch()
        reviews = {r['claim_id']: r['reason_code'] for r in read_psv(REVIEWS)}
        decisions = {r['claim_id']: r['decision'] for r in read_psv(DECISIONS)}
        assert reviews['CLM-SANC-ER'] == 'FACILITY_SANCTIONED'
        assert decisions['CLM-SANC-ER'] == 'MANUAL_REVIEW'
        assert read_psv(CHECKS) == []

    def test_sanctioned_and_untrusted_facilities_do_not_emit_payment_side_effects(self):
        """Blocked facilities must enter review and must not write check or ledger rows."""
        reset_out()
        write_base_config()
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231'], ['POL-B','MEM-B','ACTIVE','CATA','20260101','20261231']
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-BLOCK','EVT-BLOCK','POL-A','MEM-A','FAC-BLOCK','DX-CATA','20000','CHECK','','ID1','APPROVED','AUTH1','B2','20260613080000'],
            ['CLM-UNTRUST','EVT-UNTRUST','POL-B','MEM-B','FAC-UNTRUST','DX-CATA','20000','CHECK','','ID2','APPROVED','AUTH2','B2','20260613080100'],
        ])
        run_batch()
        reviews = {r['claim_id']: r['reason_code'] for r in read_psv(REVIEWS)}
        decisions = {r['claim_id']: r['decision'] for r in read_psv(DECISIONS)}
        assert reviews == {'CLM-BLOCK': 'FACILITY_SANCTIONED', 'CLM-UNTRUST': 'FACILITY_NOT_TRUSTED'}
        assert decisions['CLM-BLOCK'] == 'MANUAL_REVIEW'
        assert decisions['CLM-UNTRUST'] == 'MANUAL_REVIEW'
        assert read_psv(CHECKS) == []
        assert not LEDGER.exists() or read_psv(LEDGER) == []

    def test_untrusted_facility_with_emergency_override_may_queue_check(self):
        """An untrusted facility with emergency override may still queue a check payment."""
        reset_out()
        write_base_config(expedited=50000)
        write_psv(FACILITIES, ['facility_id','trust_tier','sanctioned','emergency_override'], [
            ['FAC-TRUST','TRUSTED','N','N'], ['FAC-STD','STANDARD','N','N'], ['FAC-ER','STANDARD','N','Y'], ['FAC-BLOCK','UNTRUSTED','Y','N'], ['FAC-UNTRUST','UNTRUSTED','N','N'], ['FAC-UNTRUST-ER','UNTRUSTED','N','Y']
        ])
        write_psv(POLICIES, ['policy_id','member_id','status','coverage_class','effective_from','effective_to'], [
            ['POL-A','MEM-A','ACTIVE','CATA','20260101','20261231']
        ])
        write_psv(CLAIMS, ['claim_id','event_id','policy_id','member_id','facility_id','diagnosis_code','amount_cents','payee_type','bank_account','identity_token','adjudication_status','auth_code','batch_id','received_ts'], [
            ['CLM-UNTRUST-ER','EVT-UNTRUST-ER','POL-A','MEM-A','FAC-UNTRUST-ER','DX-EMERG','20000','CHECK','','ID9','APPROVED','','B2','20260613080400'],
        ])
        run_batch()
        reviews = {r['claim_id'] for r in read_psv(REVIEWS)}
        checks = {r['claim_id']: r for r in read_psv(CHECKS)}
        decisions = {r['claim_id']: r['decision'] for r in read_psv(DECISIONS)}
        assert 'CLM-UNTRUST-ER' not in reviews
        assert 'CLM-UNTRUST-ER' in checks
        assert checks['CLM-UNTRUST-ER']['priority'] == 'EXPEDITED'
        assert decisions['CLM-UNTRUST-ER'] == 'PAYMENT_QUEUED'
