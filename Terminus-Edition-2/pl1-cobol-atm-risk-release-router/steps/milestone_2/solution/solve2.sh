#!/bin/bash
set -euo pipefail
cat > /app/src/atm_release_runtime.py <<'INNERPY'
#!/usr/bin/env python3
import csv
import os
import re
from pathlib import Path

STAGE = 2
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

def norm(s):
    return (s or '').strip().upper()

def parse_deck(path):
    vals = {}
    if not path.exists():
        return vals
    for line in path.read_text().splitlines():
        m = re.search(r"DCL\s+(\w+)\s+[^;]*?INIT\((?:'([^']*)'|([0-9]+))\)", line, re.I)
        if m:
            vals[m.group(1).upper()] = (m.group(2) if m.group(2) is not None else m.group(3)).strip()
    return vals

def rows(path, delim='|'):
    if not path.exists():
        return []
    with path.open(newline='') as handle:
        return [{k: (v or '').strip() for k, v in row.items()} for row in csv.DictReader(handle, delimiter=delim)]

def write_psv(path, header, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter='|', lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)

def load_rules():
    vals = parse_deck(RULES)
    aliases = {}
    for key, value in vals.items():
        if key.startswith('ALIAS_') and '=>' in value:
            left, right = value.split('=>', 1)
            aliases[norm(left)] = norm(right)
    return {
        'eligible_status': norm(vals.get('ELIGIBLE_HOLD_STATUS', 'HELD')),
        'open_state': norm(vals.get('OPEN_WINDOW_STATUS', 'OPEN')),
        'reasons': {norm(vals.get('REASON_APPROVE', 'CLEAR')), norm(vals.get('REASON_REVIEW', 'REVIEW')), norm(vals.get('REASON_EXPIRE', 'EXPIRE'))},
        'aliases': aliases,
    }

def load_risk():
    vals = parse_deck(RISK)
    def intval(name, default):
        try:
            return int(vals.get(name, default))
        except ValueError:
            return int(default)
    return {
        'daily_amount': intval('DAILY_RELEASE_LIMIT_CENTS', 80000),
        'daily_count': intval('DAILY_RELEASE_COUNT_LIMIT', 3),
        'high_value': intval('HIGH_VALUE_RELEASE_CENTS', 40000),
        'review_flag': norm(vals.get('REVIEW_RISK_FLAG', 'WATCHLIST')),
        'trusted_limit': intval('TRUSTED_TERMINAL_LIMIT_CENTS', 70000),
        'standard_limit': intval('STANDARD_TERMINAL_LIMIT_CENTS', 35000),
    }

def canon_channel(ch, aliases):
    c = norm(ch)
    return aliases.get(c, c)

def numeric_ts(s):
    return bool(re.fullmatch(r'\d{14}', (s or '').strip()))

def in_window(rel, hold, windows, rules):
    if not numeric_ts(rel.get('release_ts')) or not numeric_ts(hold.get('hold_ts')):
        return False
    if rel['release_ts'] <= hold['hold_ts']:
        return False
    for w in windows:
        if w.get('terminal_id') != rel.get('terminal_id'):
            continue
        if norm(w.get('state')) != rules['open_state']:
            continue
        if w.get('open_ts') <= hold.get('hold_ts') and rel.get('release_ts') <= w.get('close_ts'):
            return True
    return False

def load_existing_commits():
    committed = set()
    if JOURNAL.exists():
        for row in rows(JOURNAL):
            if row.get('commit_status') == 'COMMITTED':
                committed.add(row.get('release_id'))
    return committed

def rewrite_journal(existing_rows, new_rows):
    header = ['journal_seq','release_id','card_id','terminal_id','amount_cents','decision','commit_status']
    all_rows = existing_rows + new_rows
    for i, row in enumerate(all_rows, 1):
        row['journal_seq'] = str(i)
    write_psv(JOURNAL, header, all_rows)

def risk_reason(rel, amount, exposure, trust, risk):
    tier = norm(trust.get('trust_tier', 'STANDARD')) if trust else 'MISSING'
    if tier in {'BLOCKED', 'UNTRUSTED', 'MISSING'}:
        return 'BLOCKED_TERMINAL'
    if risk['review_flag'] and risk['review_flag'] in {norm(x) for x in exposure.get('risk_flags','').split(',')}:
        return 'WATCHLIST_CARD'
    released = int(exposure.get('released_today_cents', '0') or 0)
    count = int(exposure.get('release_count_today', '0') or 0)
    if count + 1 > risk['daily_count']:
        return 'DAILY_COUNT_LIMIT'
    if released + amount > risk['daily_amount']:
        return 'DAILY_AMOUNT_LIMIT'
    term_limit = int(trust.get('max_release_cents') or (risk['trusted_limit'] if tier == 'TRUSTED' else risk['standard_limit']))
    supervisor_above = int(trust.get('supervisor_above_cents') or risk['high_value'])
    if amount > term_limit or amount > supervisor_above:
        return 'HIGH_VALUE_RELEASE'
    if int(exposure.get('active_hold_cents', '0') or 0) < amount:
        return 'INSUFFICIENT_EXPOSURE'
    return ''

def apply_exposure(exp, amount):
    exp['active_hold_cents'] = str(int(exp.get('active_hold_cents','0') or 0) - amount)
    exp['released_today_cents'] = str(int(exp.get('released_today_cents','0') or 0) + amount)
    exp['release_count_today'] = str(int(exp.get('release_count_today','0') or 0) + 1)

def main():
    APP.joinpath('out').mkdir(parents=True, exist_ok=True)
    rules = load_rules()
    risk = load_risk()
    holds = rows(HOLDS)
    releases = rows(RELEASES)
    windows = rows(WINDOWS)
    exposure_source = EXPOSURE_OUT if STAGE >= 4 and EXPOSURE_OUT.exists() else EXPOSURE
    exposures = {r['card_id']: dict(r) for r in rows(exposure_source)}
    trusts = {r['terminal_id']: dict(r) for r in rows(TRUST)}
    approvals = {r['release_id']: dict(r) for r in rows(APPROVALS)}
    committed_existing = load_existing_commits() if STAGE >= 4 else set()
    existing_journal_rows = rows(JOURNAL) if JOURNAL.exists() and STAGE >= 4 else []
    for h in holds:
        h['_used'] = False
    out = []
    decisions = []
    reviews = []
    new_journal = []
    matched_count = unmatched_count = matched_amount = unmatched_amount = 0
    reviewed_count = reviewed_amount = 0
    committed_count = 0
    abend_limit = os.environ.get('ABEND_AFTER_COMMITS')
    abend_limit = int(abend_limit) if abend_limit else None
    for rel in releases:
        if STAGE >= 4 and rel['release_id'] in committed_existing:
            continue
        amount = int(rel['amount_cents']) if rel.get('amount_cents','').isdigit() else 0
        rel_chan = canon_channel(rel.get('channel'), rules['aliases']) if STAGE >= 2 else (rel.get('channel') or '').strip()
        candidates = []
        for idx, hold in enumerate(holds):
            if hold['_used']:
                continue
            hold_chan = canon_channel(hold.get('channel'), rules['aliases']) if STAGE >= 2 else (hold.get('channel') or '').strip()
            if hold.get('hold_id') != rel.get('hold_id') or hold.get('card_id') != rel.get('card_id') or hold.get('terminal_id') != rel.get('terminal_id'):
                continue
            if hold.get('region') != rel.get('region') or hold.get('amount_cents') != rel.get('amount_cents'):
                continue
            if norm(hold.get('status')) != rules['eligible_status'] or norm(rel.get('reason')) not in rules['reasons']:
                continue
            if hold_chan != rel_chan:
                continue
            if STAGE >= 3 and not in_window(rel, hold, windows, rules):
                continue
            candidates.append((hold.get('hold_ts',''), -idx, idx, hold_chan))
        match_idx = None
        chosen_chan = ''
        if candidates:
            _, _, match_idx, chosen_chan = max(candidates)
        if match_idx is None:
            unmatched_count += 1
            unmatched_amount += amount
            out.append([rel['release_id'], rel['hold_id'], rel['card_id'], rel['terminal_id'], '', rel['amount_cents'], rel['reason'], 'UNMATCHED'])
            if STAGE >= 3:
                decisions.append({'release_id':rel['release_id'],'card_id':rel['card_id'],'terminal_id':rel['terminal_id'],'risk_decision':'UNMATCHED','reason_code':'NO_ELIGIBLE_HOLD','amount_cents':rel['amount_cents']})
            continue
        holds[match_idx]['_used'] = True
        exp = exposures.get(rel['card_id'])
        if STAGE >= 2 and not exp:
            unmatched_count += 1
            unmatched_amount += amount
            out.append([rel['release_id'], rel['hold_id'], rel['card_id'], rel['terminal_id'], '', rel['amount_cents'], rel['reason'], 'UNMATCHED'])
            continue
        if STAGE == 2 and int(exp.get('active_hold_cents','0') or 0) < amount:
            unmatched_count += 1
            unmatched_amount += amount
            out.append([rel['release_id'], rel['hold_id'], rel['card_id'], rel['terminal_id'], '', rel['amount_cents'], rel['reason'], 'UNMATCHED'])
            continue
        if STAGE >= 3:
            reason = risk_reason(rel, amount, exp, trusts.get(rel['terminal_id']), risk)
            approved = STAGE >= 4 and approvals.get(rel['release_id'],{}).get('status') == 'APPROVED'
            if reason and not approved:
                reviewed_count += 1
                reviewed_amount += amount
                out.append([rel['release_id'], rel['hold_id'], rel['card_id'], rel['terminal_id'], chosen_chan, rel['amount_cents'], rel['reason'], 'REVIEW'])
                decisions.append({'release_id':rel['release_id'],'card_id':rel['card_id'],'terminal_id':rel['terminal_id'],'risk_decision':'MANUAL_REVIEW','reason_code':reason,'amount_cents':rel['amount_cents']})
                reviews.append({'release_id':rel['release_id'],'card_id':rel['card_id'],'terminal_id':rel['terminal_id'],'reason_code':reason,'amount_cents':rel['amount_cents'],'required_action':'SUPERVISOR_REVIEW'})
                continue
        if STAGE >= 2:
            apply_exposure(exp, amount)
        matched_count += 1
        matched_amount += amount
        out.append([rel['release_id'], rel['hold_id'], rel['card_id'], rel['terminal_id'], chosen_chan, rel['amount_cents'], rel['reason'], 'MATCHED'])
        if STAGE >= 3:
            decisions.append({'release_id':rel['release_id'],'card_id':rel['card_id'],'terminal_id':rel['terminal_id'],'risk_decision':'COMMITTED_RELEASE','reason_code':'APPROVED_REVIEW' if rel['release_id'] in approvals else 'AUTO_RELEASE','amount_cents':rel['amount_cents']})
        if STAGE >= 4:
            new_journal.append({'journal_seq':'','release_id':rel['release_id'],'card_id':rel['card_id'],'terminal_id':rel['terminal_id'],'amount_cents':rel['amount_cents'],'decision':'RELEASED','commit_status':'COMMITTED'})
            committed_count += 1
            rewrite_journal(existing_journal_rows, new_journal)
            write_psv(EXPOSURE_OUT, ['card_id','business_date','active_hold_cents','released_today_cents','release_count_today','risk_flags'], sorted(exposures.values(), key=lambda r:r['card_id']))
            CHECKPOINT.write_text(f"last_committed_release_id={rel['release_id']}\ncommitted_count={len(existing_journal_rows)+len(new_journal)}\n")
            if abend_limit is not None and committed_count >= abend_limit:
                raise SystemExit(77)
    with REPORT.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['release_id','hold_id','card_id','terminal_id','channel','amount_cents','reason','status'])
        writer.writerows(out)
    SUMMARY.write_text(
        f'matched_count={matched_count}\nmatched_amount_cents={matched_amount}\n'
        f'unmatched_count={unmatched_count}\nunmatched_amount_cents={unmatched_amount}\n'
        + (f'review_count={reviewed_count}\nreview_amount_cents={reviewed_amount}\n' if STAGE >= 3 else '')
    )
    if STAGE >= 2:
        write_psv(EXPOSURE_OUT, ['card_id','business_date','active_hold_cents','released_today_cents','release_count_today','risk_flags'], sorted(exposures.values(), key=lambda r:r['card_id']))
    if STAGE >= 3:
        write_psv(DECISIONS, ['release_id','card_id','terminal_id','risk_decision','reason_code','amount_cents'], decisions)
        write_psv(REVIEW_QUEUE, ['release_id','card_id','terminal_id','reason_code','amount_cents','required_action'], reviews)
    if STAGE >= 4 and not JOURNAL.exists():
        rewrite_journal([], [])

if __name__ == '__main__':
    main()

INNERPY
cat > /app/src/atm_release_router.cbl <<'INNERCOB'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. atm-release-router.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 PY-COMMAND PIC X(80) VALUE "python3 /app/src/atm_release_runtime.py".
       01 PY-STATUS PIC S9(9) COMP-5 VALUE 0.
       01 PY-EXIT PIC S9(9) COMP-5 VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "SYSTEM" USING PY-COMMAND RETURNING PY-STATUS
           COMPUTE PY-EXIT = PY-STATUS / 256
           STOP RUN PY-EXIT.
INNERCOB
