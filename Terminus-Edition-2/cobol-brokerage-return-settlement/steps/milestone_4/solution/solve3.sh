#!/usr/bin/env bash
set -euo pipefail
cd /app
LEVEL=3
cat > /app/src/wire_returns_runner.py <<'PY'
import csv
from pathlib import Path

APP = Path('/app')
LEVEL = int(Path('/app/src/.wire_returns_level').read_text().strip())
WIRES = APP / 'data' / 'wires.dat'
RETURNS = APP / 'data' / 'returns.dat'
CALENDAR = APP / 'config' / 'cycle_calendar.txt'
REASONS = APP / 'config' / 'reason_codes.csv'
REPORT = APP / 'out' / 'wire_return_report.csv'
SUMMARY = APP / 'out' / 'wire_return_summary.txt'
BASE_REASONS = {'CON', 'REF', 'ADM', 'B2B'}


def field(line, start, end):
    return line[start:end]


def parse_wires():
    rows = []
    if not WIRES.exists():
        return rows
    for idx, raw in enumerate(WIRES.read_text().splitlines()):
        line = raw.rstrip('\n')
        if not line:
            continue
        rows.append({
            'idx': idx,
            'wire_id': field(line, 1, 13).strip(),
            'reason': field(line, 13, 16).strip(),
            'amount_text': field(line, 16, 26),
            'amount': int((field(line, 16, 26).strip() or '0')),
            'account_id': field(line, 26, 34).strip(),
            'status': field(line, 34, 35).strip().upper(),
            'settle_date': field(line, 35, 43).strip(),
            'used': False,
        })
    return rows


def parse_returns():
    rows = []
    if not RETURNS.exists():
        return rows
    for idx, raw in enumerate(RETURNS.read_text().splitlines()):
        line = raw.rstrip('\n')
        if not line:
            continue
        rows.append({
            'idx': idx,
            'wire_id': field(line, 1, 13).strip(),
            'amount_text': field(line, 13, 23),
            'amount': int((field(line, 13, 23).strip() or '0')),
            'account_id': field(line, 23, 31).strip(),
            'return_date': field(line, 31, 39).strip(),
            'return_reason': field(line, 39, 42).strip().upper(),
        })
    return rows


def load_calendar():
    open_days = {}
    if not CALENDAR.exists():
        return open_days
    for raw in CALENDAR.read_text().splitlines():
        parts = raw.split()
        if len(parts) >= 2 and len(parts[0]) == 8:
            open_days[parts[0]] = parts[1].upper() == 'OPEN'
    return open_days


def load_policy():
    policy = {}
    if not REASONS.exists():
        return {code: {'enabled': True, 'priority': 9999} for code in BASE_REASONS}
    with REASONS.open(newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = (row.get('code') or '').strip().upper()
            if not code:
                continue
            raw_priority = (row.get('priority') or '').strip()
            try:
                priority = int(raw_priority)
                if priority <= 0:
                    priority = 9999
            except ValueError:
                priority = 9999
            policy[code] = {
                'enabled': (row.get('enabled') or '').strip().lower() == 'true',
                'priority': priority,
            }
    return policy


def cycle_ok(wire, ret, open_days):
    wire_date = wire['settle_date']
    return_date = ret['return_date']
    if not wire_date and not return_date:
        return True
    if not wire_date or not return_date:
        return False
    if not open_days.get(wire_date, False) or not open_days.get(return_date, False):
        return False
    if return_date < wire_date:
        return False
    open_count = sum(
        1 for day, is_open in open_days.items()
        if is_open and wire_date < day <= return_date
    )
    return open_count <= 2


def base_candidate(wire, ret):
    return (
        not wire['used']
        and wire['wire_id'] == ret['wire_id']
        and wire['account_id'] == ret['account_id']
        and wire['amount_text'] == ret['amount_text']
        and wire['status'] == 'S'
    )


def reason_enabled(wire, policy):
    if LEVEL < 4:
        return wire['reason'] in BASE_REASONS
    return policy.get(wire['reason'], {}).get('enabled', False)


def reason_matches(wire, ret, policy):
    if not reason_enabled(wire, policy):
        return False
    if LEVEL < 4:
        return True
    requested = ret['return_reason']
    if requested == 'ANY' or requested == '':
        return True
    return wire['reason'] == requested


def selection_key(wire, ret, policy):
    if LEVEL >= 4 and ret['return_reason'] == 'ANY':
        priority = policy.get(wire['reason'], {}).get('priority', 9999)
        return (wire['settle_date'], -priority, -wire['idx'])
    return (wire['settle_date'], -wire['idx'])


def find_match(wires, ret, open_days, policy):
    matches = []
    for wire in wires:
        if not base_candidate(wire, ret):
            continue
        if LEVEL >= 3 and not cycle_ok(wire, ret, open_days):
            continue
        if not reason_matches(wire, ret, policy):
            continue
        matches.append(wire)
    if not matches:
        return None
    if LEVEL >= 3:
        return max(matches, key=lambda wire: selection_key(wire, ret, policy))
    return matches[0]


def main():
    wires = parse_wires()
    returns = parse_returns()
    open_days = load_calendar()
    policy = load_policy()
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    cleared_count = 0
    cleared_amount = 0
    exception_count = 0
    exception_amount = 0
    rows = []

    for ret in returns:
        match = find_match(wires, ret, open_days, policy)
        if match is not None:
            match['used'] = True
            cleared_count += 1
            cleared_amount += ret['amount']
            rows.append({
                'wire_id': ret['wire_id'],
                'account_id': ret['account_id'],
                'reason': match['reason'],
                'amount_cents': ret['amount_text'],
                'status': 'CLEARED',
            })
        else:
            exception_count += 1
            exception_amount += ret['amount']
            rows.append({
                'wire_id': ret['wire_id'],
                'account_id': ret['account_id'],
                'reason': '',
                'amount_cents': ret['amount_text'],
                'status': 'EXCEPTION',
            })

    with REPORT.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['wire_id', 'account_id', 'reason', 'amount_cents', 'status'])
        writer.writeheader()
        writer.writerows(rows)
    SUMMARY.write_text(
        f'cleared_count={cleared_count}\n'
        f'cleared_amount_cents={cleared_amount}\n'
        f'exception_count={exception_count}\n'
        f'exception_amount_cents={exception_amount}\n'
    )


if __name__ == '__main__':
    main()
PY
printf '%s\n' "$LEVEL" > /app/src/.wire_returns_level
cat > /app/src/wire_returns.cbl <<'CBL'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. WIRE-RETURNS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 RUN-COMMAND PIC X(128) VALUE "python3 /app/src/wire_returns_runner.py".
       PROCEDURE DIVISION.
           CALL "SYSTEM" USING RUN-COMMAND
           STOP RUN.
CBL
/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt