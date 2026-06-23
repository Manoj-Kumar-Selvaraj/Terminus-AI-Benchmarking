#!/usr/bin/env python3
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

APP = Path('/app')

REPORT_HDR = ['audit_id', 'frame_id', 'craft_id', 'channel', 'service_class', 'payload_hash', 'verdict_code', 'status']
CONSUMPTION_HDR = ['audit_id', 'catalog_row', 'recv_ts', 'frame_id']
SUMMARY_KEYS = ['matched_count', 'matched_frames', 'rejected_count', 'rejected_frames']
LEDGER_HDR = ['pass_id', 'craft_id', 'channel', 'vcid', 'seq', 'frame_id', 'recv_ts', 'payload_hash', 'status']
QUAR_HDR = ['source_file', 'line_no', 'pass_id', 'craft_id', 'channel', 'vcid', 'seq', 'frame_id', 'reason']
RECOVERY_KEYS = ['segments_seen', 'frames_seen', 'frames_committed', 'duplicates_suppressed', 'frames_quarantined', 'checkpoint_status']
ANOM_HDR = ['pass_id', 'craft_id', 'channel', 'vcid', 'seq', 'frame_id', 'reason', 'detail']
CONFLICT_HDR = ['pass_id', 'craft_id', 'channel', 'vcid', 'seq', 'frame_id', 'station_id', 'reason', 'detail']


def trim(x: object) -> str:
    return str(x or '').strip()


def up(x: object) -> str:
    return trim(x).upper()


def is_ts(x: str) -> bool:
    return bool(re.fullmatch(r'\d{14}', trim(x)))


def read_psv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    text = path.read_text().splitlines()
    if not text:
        return []
    header = [h.strip() for h in text[0].split('|')]
    rows: list[dict[str, str]] = []
    for line in text[1:]:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split('|')]
        row = {h: (parts[i] if i < len(parts) else '') for i, h in enumerate(header)}
        rows.append(row)
    return rows


def write_psv(path: Path, header: list[str], rows: list[dict[str, str] | list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        f.write('|'.join(header) + '\n')
        for row in rows:
            if isinstance(row, dict):
                f.write('|'.join(trim(row.get(h, '')) for h in header) + '\n')
            else:
                f.write('|'.join(trim(v) for v in row) + '\n')


def parse_rules() -> tuple[dict[str, str], dict[str, str]]:
    rules: dict[str, str] = {}
    aliases: dict[str, str] = {}
    path = APP / 'src/audit_rules.pli'
    if not path.exists():
        return rules, aliases
    pat = re.compile(r"^\s*DCL\s+([A-Za-z0-9_]+).*?INIT\('\s*(.*?)\s*'\)", re.I)
    for line in path.read_text().splitlines():
        m = pat.search(line)
        if not m:
            continue
        name = m.group(1).upper()
        val = trim(m.group(2))
        rules[name] = val
        if name.startswith('ALIAS_') and '=>' in val:
            raw, canon = val.split('=>', 1)
            aliases[up(raw)] = up(canon)
            aliases[up(canon)] = up(canon)
    return rules, aliases


def parse_batch() -> dict[str, str]:
    flags = {'KEY_COMPARE': 'PREFIX5', 'CONSUME': 'OFF', 'ALIAS_MODE': 'OFF', 'WINDOW_MODE': 'OFF'}
    path = APP / 'src/audit_batch.pli'
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == '%SET':
                flags[parts[1].upper()] = parts[2].upper()
    return flags


def make_canon(aliases: dict[str, str], alias_mode: bool):
    def canon(x: object) -> str:
        k = up(x)
        return aliases.get(k, k) if alias_mode else k
    return canon


def audit_static(rules: dict[str, str], aliases: dict[str, str], flags: dict[str, str]) -> None:
    canon = make_canon(aliases, flags.get('ALIAS_MODE') == 'ON')
    window_mode = flags.get('WINDOW_MODE') == 'ON'
    consume_on = flags.get('CONSUME') == 'ON'
    full_key = flags.get('KEY_COMPARE') == 'FULL'
    catalog = read_psv(APP / 'data/catalog.psv')
    audits = read_psv(APP / 'data/audits.psv')
    windows = read_psv(APP / 'config/pass_windows.psv') if window_mode else []
    eligible = up(rules.get('ELIGIBLE_STATE', ''))
    verdicts = {up(rules.get(f'VERDICT_{c}', '')) for c in 'ABC'} - {''}
    open_state = up(rules.get('OPEN_PASS_STATE', ''))
    used: set[int] = set()

    def keys_ok(c: dict[str, str], a: dict[str, str]) -> bool:
        if not full_key:
            return trim(c.get('frame_id'))[:5] == trim(a.get('frame_id'))[:5] and trim(c.get('payload_hash')) == trim(a.get('payload_hash'))
        return (
            trim(c.get('frame_id')) == trim(a.get('frame_id'))
            and canon(c.get('craft_id')) == canon(a.get('craft_id'))
            and canon(c.get('channel')) == canon(a.get('channel'))
            and trim(c.get('payload_hash')) == trim(a.get('payload_hash'))
            and canon(c.get('service_class')) == canon(a.get('service_class'))
        )

    def win_ok(c: dict[str, str], a: dict[str, str]) -> bool:
        if not window_mode:
            return True
        recv_ts = trim(c.get('recv_ts'))
        audit_ts = trim(a.get('audit_ts'))
        if not (is_ts(recv_ts) and is_ts(audit_ts)):
            return False
        cc = canon(c.get('craft_id'))
        ch = canon(c.get('channel'))
        for w in windows:
            open_ts, close_ts = trim(w.get('open_ts')), trim(w.get('close_ts'))
            if not (is_ts(open_ts) and is_ts(close_ts)):
                continue
            if canon(w.get('craft_id')) != cc:
                continue
            if 'channel' in w and trim(w.get('channel')) and canon(w.get('channel')) != ch:
                continue
            if up(w.get('state')) != open_state:
                continue
            if open_ts <= recv_ts <= close_ts and recv_ts <= audit_ts <= close_ts:
                return True
        return False

    rows: list[dict[str, str]] = []
    consumption: list[dict[str, str]] = []
    matched = rejected = 0
    for a in audits:
        best_idx: int | None = None
        for idx, c in enumerate(catalog):
            if consume_on and idx in used:
                continue
            if not keys_ok(c, a):
                continue
            if up(c.get('state')) != eligible:
                continue
            if up(a.get('verdict_code')) not in verdicts:
                continue
            if not win_ok(c, a):
                continue
            if best_idx is None:
                best_idx = idx
            else:
                best = catalog[best_idx]
                if trim(c.get('recv_ts')) > trim(best.get('recv_ts')) or (trim(c.get('recv_ts')) == trim(best.get('recv_ts')) and idx < best_idx):
                    best_idx = idx
        if best_idx is None:
            rejected += 1
            sc = ''
            status = 'REJECTED'
        else:
            if consume_on:
                used.add(best_idx)
            matched += 1
            sc = canon(catalog[best_idx].get('service_class'))
            status = 'ACCEPTED'
            consumption.append({
                'audit_id': trim(a.get('audit_id')),
                'catalog_row': str(best_idx),
                'recv_ts': trim(catalog[best_idx].get('recv_ts')),
                'frame_id': trim(catalog[best_idx].get('frame_id')),
            })
        rows.append({
            'audit_id': trim(a.get('audit_id')),
            'frame_id': trim(a.get('frame_id')),
            'craft_id': trim(a.get('craft_id')),
            'channel': trim(a.get('channel')),
            'service_class': sc,
            'payload_hash': trim(a.get('payload_hash')),
            'verdict_code': trim(a.get('verdict_code')),
            'status': status,
        })
    write_psv(APP / 'out/audit_report.csv', REPORT_HDR, rows)
    write_psv(APP / 'out/catalog_consumption.psv', CONSUMPTION_HDR, consumption)
    summary = {'matched_count': str(matched), 'matched_frames': str(matched), 'rejected_count': str(rejected), 'rejected_frames': str(rejected)}
    (APP / 'out').mkdir(parents=True, exist_ok=True)
    (APP / 'out/audit_summary.txt').write_text(''.join(f'{k}={summary[k]}\n' for k in SUMMARY_KEYS))


def window_ok_for_frame(frame: dict[str, str], rules: dict[str, str], aliases: dict[str, str]) -> bool:
    canon = make_canon(aliases, True)
    windows = read_psv(APP / 'config/pass_windows.psv')
    recv_ts = trim(frame.get('recv_ts'))
    if not is_ts(recv_ts):
        return False
    open_state = up(rules.get('OPEN_PASS_STATE', ''))
    for w in windows:
        o, c = trim(w.get('open_ts')), trim(w.get('close_ts'))
        if not (is_ts(o) and is_ts(c)):
            continue
        if canon(w.get('craft_id')) != canon(frame.get('craft_id')):
            continue
        if 'channel' in w and trim(w.get('channel')) and canon(w.get('channel')) != canon(frame.get('channel')):
            continue
        if up(w.get('state')) != open_state:
            continue
        if o <= recv_ts <= c:
            return True
    return False


def checkpoint_status(ledger: list[dict[str, str]]) -> str:
    cp_path = APP / 'state/downlink_checkpoint.psv'
    cps = read_psv(cp_path)
    if not cp_path.exists() or not cps:
        return 'MISSING'
    max_by_stream: dict[tuple[str, str, str, str], int] = {}
    for r in ledger:
        if up(r.get('status')) != 'COMMITTED' or not trim(r.get('seq')).isdigit():
            continue
        key = (up(r.get('pass_id')), up(r.get('craft_id')), up(r.get('channel')), up(r.get('vcid')))
        max_by_stream[key] = max(max_by_stream.get(key, -1), int(trim(r.get('seq'))))
    status = 'OK'
    for cp in cps:
        if not trim(cp.get('last_seq')).isdigit():
            continue
        key = (up(cp.get('pass_id')), up(cp.get('craft_id')), up(cp.get('channel')), up(cp.get('vcid')))
        last = int(trim(cp.get('last_seq')))
        mx = max_by_stream.get(key, -1)
        if last > mx:
            return 'AHEAD_OF_LEDGER'
        if last < mx:
            status = 'STALE'
    return status


def parse_spool(rules: dict[str, str], aliases: dict[str, str]):
    canon = make_canon(aliases, True)
    spool = APP / 'spool/downlink_segments'
    spool.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, str]] = []
    quarantine: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    segments_seen = 0
    frames_seen = 0
    headers: dict[tuple[str, str, str], dict[str, str]] = {}
    trailers: dict[tuple[str, str, str], dict[str, str]] = {}
    structured_frames_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    seen_trailer_keys: set[tuple[str, str, str]] = set()

    def q(source, line_no, parts, reason):
        data = parts + [''] * 12
        quarantine.append({'source_file': source, 'line_no': str(line_no), 'pass_id': data[0], 'craft_id': data[3] if len(parts) >= 4 else '', 'channel': data[4] if len(parts) >= 5 else '', 'vcid': data[5] if len(parts) >= 6 else '', 'seq': data[6] if len(parts) >= 7 else '', 'frame_id': data[7] if len(parts) >= 8 else '', 'reason': reason})

    for path in sorted(p for p in spool.iterdir() if p.is_file() and p.suffix in {'.seg', '.replay', '.partial'}):
        segments_seen += 1
        is_partial = path.suffix == '.partial'
        for line_no, raw in enumerate(path.read_text().splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split('|')]
            frames_seen += 1
            if is_partial:
                q(path.name, line_no, parts, 'PARTIAL_SEGMENT')
                continue
            if parts[0] == 'HDR':
                if len(parts) != 7:
                    q(path.name, line_no, parts, 'MALFORMED_FRAME')
                    continue
                key = (parts[1], parts[2], parts[3])
                headers[key] = {'pass_id': parts[1], 'segment_id': parts[2], 'station_id': parts[3], 'craft_id': canon(parts[4]), 'channel': canon(parts[5]), 'opened_ts': parts[6], 'source_file': path.name, 'line_no': str(line_no)}
                continue
            if parts[0] == 'TRL':
                if len(parts) != 7:
                    q(path.name, line_no, parts, 'MALFORMED_FRAME')
                    continue
                key = (parts[1], parts[2], parts[3])
                trailers[key] = {'pass_id': parts[1], 'segment_id': parts[2], 'station_id': parts[3], 'frame_count': parts[4], 'hash_total': parts[5], 'closed_ts': parts[6], 'source_file': path.name, 'line_no': str(line_no)}
                seen_trailer_keys.add(key)
                continue
            if parts[0] == 'FRM':
                if len(parts) != 13:
                    q(path.name, line_no, parts, 'MALFORMED_FRAME')
                    continue
                f = {'source_file': path.name, 'line_no': str(line_no), 'pass_id': parts[1], 'segment_id': parts[2], 'station_id': parts[3], 'craft_id': canon(parts[4]), 'channel': canon(parts[5]), 'vcid': parts[6], 'seq': parts[7], 'frame_id': parts[8], 'recv_ts': parts[9], 'payload_hash': parts[10], 'crc_status': parts[11], 'segment_status': parts[12], 'structured': '1'}
                key = (f['pass_id'], f['segment_id'], f['station_id'])
                f['after_trailer'] = '1' if key in seen_trailer_keys else '0'
                frames.append(f)
                structured_frames_by_key[key].append(f)
                continue
            if len(parts) != 12:
                q(path.name, line_no, parts, 'MALFORMED_FRAME')
                continue
            frames.append({'source_file': path.name, 'line_no': str(line_no), 'pass_id': parts[0], 'segment_id': parts[1], 'station_id': parts[2], 'craft_id': canon(parts[3]), 'channel': canon(parts[4]), 'vcid': parts[5], 'seq': parts[6], 'frame_id': parts[7], 'recv_ts': parts[8], 'payload_hash': parts[9], 'crc_status': parts[10], 'segment_status': parts[11], 'structured': '0', 'after_trailer': '0'})

    invalid_lines: set[tuple[str, str]] = set()
    all_structured = [f for f in frames if f.get('structured') == '1']
    any_headers_or_trailers = bool(headers or trailers)
    if any_headers_or_trailers:
        for key, flist in structured_frames_by_key.items():
            has_header = key in headers
            has_trailer = key in trailers
            for f in flist:
                if not has_header:
                    conflicts.append(conflict_from_frame(f, 'MISSING_HEADER', 'header_not_found'))
                    invalid_lines.add((f['source_file'], f['line_no']))
                if not has_trailer:
                    conflicts.append(conflict_from_frame(f, 'MISSING_TRAILER', 'trailer_not_found'))
                    invalid_lines.add((f['source_file'], f['line_no']))
                if f.get('after_trailer') == '1':
                    conflicts.append(conflict_from_frame(f, 'FRAME_AFTER_TRAILER', f"segment_id={f['segment_id']}"))
                    invalid_lines.add((f['source_file'], f['line_no']))
                if (not has_header or not has_trailer) and (headers or trailers):
                    conflicts.append(conflict_from_frame(f, 'SEGMENT_ID_MISMATCH', f"segment_id={f['segment_id']}"))
                    invalid_lines.add((f['source_file'], f['line_no']))
        for key, tr in trailers.items():
            flist = [f for f in structured_frames_by_key.get(key, []) if f.get('after_trailer') != '1']
            if not trim(tr.get('frame_count')).isdigit() or int(tr['frame_count']) != len(flist):
                conflicts.append({'pass_id': tr['pass_id'], 'craft_id': '', 'channel': '', 'vcid': '', 'seq': '', 'frame_id': '', 'station_id': tr['station_id'], 'reason': 'SEGMENT_COUNT_MISMATCH', 'detail': f"segment_id={tr['segment_id']} expected={tr['frame_count']} actual={len(flist)}"})
                for f in flist:
                    invalid_lines.add((f['source_file'], f['line_no']))
            actual_hash = str(sum(sum(f['payload_hash'].encode('ascii')) for f in flist if up(f.get('crc_status')) == 'OK' and up(f.get('segment_status')) == 'COMPLETE'))
            if trim(tr.get('hash_total')) != actual_hash:
                conflicts.append({'pass_id': tr['pass_id'], 'craft_id': '', 'channel': '', 'vcid': '', 'seq': '', 'frame_id': '', 'station_id': tr['station_id'], 'reason': 'SEGMENT_HASH_MISMATCH', 'detail': f"segment_id={tr['segment_id']} expected={tr['hash_total']} actual={actual_hash}"})
                for f in flist:
                    invalid_lines.add((f['source_file'], f['line_no']))
        # If a header and trailer exist for a segment but frames point elsewhere, surface mismatch on the orphan frames.
        matched_keys = set(headers) | set(trailers)
        for f in all_structured:
            if (f['pass_id'], f['segment_id'], f['station_id']) not in matched_keys:
                conflicts.append(conflict_from_frame(f, 'SEGMENT_ID_MISMATCH', f"segment_id={f['segment_id']}"))
                invalid_lines.add((f['source_file'], f['line_no']))

    eligible: list[dict[str, str]] = []
    for f in frames:
        if (f['source_file'], f['line_no']) in invalid_lines:
            continue
        if up(f.get('crc_status')) != 'OK':
            q(f['source_file'], f['line_no'], frame_to_plain_parts(f), 'BAD_CRC')
            continue
        if up(f.get('segment_status')) != 'COMPLETE':
            q(f['source_file'], f['line_no'], frame_to_plain_parts(f), 'INCOMPLETE_SEGMENT')
            continue
        if not window_ok_for_frame(f, rules, aliases):
            q(f['source_file'], f['line_no'], frame_to_plain_parts(f), 'PASS_CLOSED')
            continue
        eligible.append(f)
    return eligible, quarantine, conflicts, segments_seen, frames_seen


def frame_to_plain_parts(f: dict[str, str]) -> list[str]:
    return [f.get('pass_id', ''), f.get('segment_id', ''), f.get('station_id', ''), f.get('craft_id', ''), f.get('channel', ''), f.get('vcid', ''), f.get('seq', ''), f.get('frame_id', ''), f.get('recv_ts', ''), f.get('payload_hash', ''), f.get('crc_status', ''), f.get('segment_status', '')]


def conflict_from_frame(f: dict[str, str], reason: str, detail: str) -> dict[str, str]:
    return {'pass_id': f.get('pass_id', ''), 'craft_id': f.get('craft_id', ''), 'channel': f.get('channel', ''), 'vcid': f.get('vcid', ''), 'seq': f.get('seq', ''), 'frame_id': f.get('frame_id', ''), 'station_id': f.get('station_id', ''), 'reason': reason, 'detail': detail}


def load_station_priority() -> dict[tuple[str, str, str, str], dict[str, str]]:
    rows = read_psv(APP / 'config/station_priority.psv')
    table = {}
    for r in rows:
        key = (up(r.get('pass_id')), up(r.get('craft_id')), up(r.get('channel')), up(r.get('station_id')))
        table[key] = r
    return table


def resolve_station_conflicts(frames: list[dict[str, str]], conflicts: list[dict[str, str]]) -> list[dict[str, str]]:
    priority = load_station_priority()
    if not priority:
        return frames
    eligible: list[dict[str, str]] = []
    for f in frames:
        key = (up(f.get('pass_id')), up(f.get('craft_id')), up(f.get('channel')), up(f.get('station_id')))
        p = priority.get(key)
        if not p or not (is_ts(f.get('recv_ts')) and is_ts(p.get('handoff_open_ts')) and is_ts(p.get('handoff_close_ts'))) or not (trim(p.get('handoff_open_ts')) <= trim(f.get('recv_ts')) <= trim(p.get('handoff_close_ts'))):
            conflicts.append(conflict_from_frame(f, 'STATION_OUTSIDE_HANDOFF', f"station_id={f.get('station_id')}"))
            continue
        f = dict(f)
        try:
            f['_priority'] = int(trim(p.get('priority')))
        except ValueError:
            f['_priority'] = 999999
        eligible.append(f)
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for f in eligible:
        grouped[(up(f.get('pass_id')), up(f.get('craft_id')), up(f.get('channel')), up(f.get('vcid')), trim(f.get('seq')))].append(f)
    selected: list[dict[str, str]] = []
    for _key, group in grouped.items():
        group.sort(key=lambda x: (x.get('_priority', 999999), trim(x.get('recv_ts')), trim(x.get('station_id'))))
        # Exact duplicate observations from the same station are replay duplicates, not station-handoff conflicts.
        same_observation = {(trim(g.get('station_id')), trim(g.get('frame_id')), trim(g.get('payload_hash'))) for g in group}
        if len(same_observation) == 1:
            selected.extend(group)
            continue
        winner = group[0]
        selected.append(winner)
        payloads = {trim(g.get('payload_hash')) for g in group}
        for other in group[1:]:
            if len(payloads) > 1:
                conflicts.append(conflict_from_frame(other, 'PAYLOAD_CONFLICT', f"authoritative_station={winner.get('station_id')}"))
            else:
                conflicts.append(conflict_from_frame(other, 'LOWER_PRIORITY_DUPLICATE', f"authoritative_station={winner.get('station_id')}"))
    return selected


def process_replay(rules: dict[str, str], aliases: dict[str, str]) -> list[dict[str, str]]:
    ledger_path = APP / 'state/audit_ledger.psv'
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = read_psv(ledger_path)
    existing_rows = list(ledger)
    frames, quarantine, conflicts, segments_seen, frames_seen = parse_spool(rules, aliases)
    frames = resolve_station_conflicts(frames, conflicts)

    existing_sem = {(r.get('pass_id'), up(r.get('craft_id')), up(r.get('channel')), up(r.get('vcid')), trim(r.get('seq')), trim(r.get('frame_id')), trim(r.get('payload_hash'))) for r in existing_rows if up(r.get('status')) == 'COMMITTED'}
    run_seen_sem: set[tuple] = set()
    new_rows: list[dict[str, str]] = []
    duplicates = 0
    for f in frames:
        sem = (f.get('pass_id'), up(f.get('craft_id')), up(f.get('channel')), up(f.get('vcid')), trim(f.get('seq')), trim(f.get('frame_id')), trim(f.get('payload_hash')))
        if sem in existing_sem or sem in run_seen_sem:
            duplicates += 1
            continue
        run_seen_sem.add(sem)
        new_rows.append({'pass_id': f.get('pass_id', ''), 'craft_id': up(f.get('craft_id')), 'channel': up(f.get('channel')), 'vcid': f.get('vcid', ''), 'seq': f.get('seq', ''), 'frame_id': f.get('frame_id', ''), 'recv_ts': f.get('recv_ts', ''), 'payload_hash': f.get('payload_hash', ''), 'status': 'COMMITTED'})
    all_rows = existing_rows + new_rows
    write_psv(ledger_path, LEDGER_HDR, all_rows)
    write_psv(APP / 'out/quarantine.psv', QUAR_HDR, quarantine)
    write_psv(APP / 'out/station_conflicts.psv', CONFLICT_HDR, conflicts)
    status = checkpoint_status(all_rows)
    recovery = {
        'segments_seen': str(segments_seen),
        'frames_seen': str(frames_seen),
        'frames_committed': str(len(new_rows)),
        'duplicates_suppressed': str(duplicates),
        'frames_quarantined': str(len(quarantine)),
        'checkpoint_status': status,
    }
    (APP / 'out/replay_recovery_report.txt').write_text(''.join(f'{k}={recovery[k]}\n' for k in RECOVERY_KEYS))
    return all_rows


def sequence_anomalies(ledger_rows: list[dict[str, str]], aliases: dict[str, str]) -> None:
    canon = make_canon(aliases, True)
    cfg = {}
    for r in read_psv(APP / 'config/sequence_contract.psv'):
        cfg[(canon(r.get('craft_id')), canon(r.get('channel')), up(r.get('vcid')))] = r
    anomalies: list[dict[str, str]] = []
    streams: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for r in ledger_rows:
        if up(r.get('status')) != 'COMMITTED':
            continue
        cr, ch, vc = canon(r.get('craft_id')), canon(r.get('channel')), up(r.get('vcid'))
        streams[(up(r.get('pass_id')), cr, ch, vc)].append({**r, 'craft_id': cr, 'channel': ch, 'vcid': vc})
    for (pass_id, craft, channel, vcid), rows in streams.items():
        c = cfg.get((craft, channel, vcid), {'min_seq': '000000', 'max_seq': '999999', 'wrap_enabled': 'N'})
        min_seq = int(c.get('min_seq', '0')) if trim(c.get('min_seq', '0')).isdigit() else 0
        max_seq = int(c.get('max_seq', '999999')) if trim(c.get('max_seq', '999999')).isdigit() else 999999
        width = max(len(trim(c.get('min_seq', '000000'))), len(trim(c.get('max_seq', '999999'))), 6)
        valid_by_seq: dict[int, list[dict[str, str]]] = defaultdict(list)
        arrival: list[tuple[str, int]] = []
        for r in rows:
            seq_s = trim(r.get('seq'))
            base = {'pass_id': pass_id, 'craft_id': craft, 'channel': channel, 'vcid': vcid, 'seq': seq_s, 'frame_id': r.get('frame_id', ''), 'reason': '', 'detail': ''}
            if not seq_s.isdigit():
                anomalies.append({**base, 'reason': 'BAD_SEQ_FORMAT', 'detail': f"seq={seq_s}"})
                continue
            seq_i = int(seq_s)
            if seq_i < min_seq or seq_i > max_seq:
                anomalies.append({**base, 'reason': 'OUT_OF_RANGE_SEQ', 'detail': f"allowed={min_seq:0{width}d}-{max_seq:0{width}d}"})
                continue
            valid_by_seq[seq_i].append(r)
            arrival.append((trim(r.get('recv_ts')), seq_i))
        for seq_i, rlist in valid_by_seq.items():
            frames = {(trim(r.get('frame_id')), trim(r.get('payload_hash'))) for r in rlist}
            if len(frames) > 1:
                r = rlist[0]
                anomalies.append({'pass_id': pass_id, 'craft_id': craft, 'channel': channel, 'vcid': vcid, 'seq': f'{seq_i:0{width}d}', 'frame_id': r.get('frame_id', ''), 'reason': 'DUPLICATE_SEQ', 'detail': f"count={len(rlist)}"})
        seqs = sorted(valid_by_seq)
        if len(seqs) >= 2:
            for a, b in zip(seqs, seqs[1:]):
                # A min/max boundary in the sorted set represents wrap ordering, not an enormous interior gap.
                if a == min_seq and b == max_seq:
                    continue
                if b > a + 1:
                    for missing in range(a + 1, b):
                        anomalies.append({'pass_id': pass_id, 'craft_id': craft, 'channel': channel, 'vcid': vcid, 'seq': f'{missing:0{width}d}', 'frame_id': '', 'reason': 'SEQ_GAP', 'detail': f"missing_after={a:0{width}d} before={b:0{width}d}"})
        arrival.sort()
        for (_, prev), (_, cur) in zip(arrival, arrival[1:]):
            if cur < prev and not (prev == max_seq and cur == min_seq and up(c.get('wrap_enabled')) == 'Y'):
                anomalies.append({'pass_id': pass_id, 'craft_id': craft, 'channel': channel, 'vcid': vcid, 'seq': f'{cur:0{width}d}', 'frame_id': '', 'reason': 'UNEXPECTED_WRAP', 'detail': f"previous={prev:0{width}d}"})
    write_psv(APP / 'out/downlink_anomalies.psv', ANOM_HDR, anomalies)


def main() -> None:
    rules, aliases = parse_rules()
    flags = parse_batch()
    audit_static(rules, aliases, flags)
    ledger_rows = process_replay(rules, aliases)
    sequence_anomalies(ledger_rows, aliases)


if __name__ == '__main__':
    main()
