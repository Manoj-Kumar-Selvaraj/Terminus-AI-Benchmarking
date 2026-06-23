#!/usr/bin/env python3
"""FNBULKUP offline driver.

This Python driver is the deterministic stand-in for the COBOL/DB2 batch job.
The public contract intentionally mirrors a mainframe job: fixed-width FB
records in, DB2-style SQLCODEs and committed side effects out.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from db2_financial_sim import (
    OK, NOT_FOUND, LOCK_TIMEOUT, CONSTRAINT, DUPLICATE,
    append_audit, append_ledger, append_pending_lock, append_reject,
    ensure_not_duplicate, is_applied, load_db, mark_applied, save_db,
    update_balance, update_hold, update_master_limit, update_rate, update_risk_limit,
)

@dataclass
class Detail:
    seq: int
    account: str
    op: str
    amount: int
    group_id: str
    event_id: str


def parse_amount(sign: str, amount: str) -> int:
    if sign not in "+-" or not amount.isdigit():
        raise ValueError("bad signed amount")
    value = int(amount)
    return -value if sign == "-" else value


def parse_file(path: Path):
    lines = [line.rstrip("\n") for line in path.read_text().splitlines() if line.rstrip("\n")]
    if len(lines) < 2 or not lines[0].startswith("H") or not lines[-1].startswith("T"):
        raise ValueError("missing header or trailer")
    header = {"batch_id": lines[0][1:11].strip(), "business_date": lines[0][11:19], "source": lines[0][19:27].strip()}
    trailer = {"batch_id": lines[-1][1:11].strip(), "count": int(lines[-1][11:17]), "total": parse_amount(lines[-1][17:18], lines[-1][18:30])}
    details: List[Detail] = []
    for raw in lines[1:-1]:
        if not raw.startswith("D"):
            raise ValueError(f"bad record type {raw[:1]}")
        details.append(Detail(
            seq=int(raw[1:7]), account=raw[7:19].strip(), op=raw[19:22].strip(),
            amount=parse_amount(raw[22:23], raw[23:35]), group_id=raw[35:41].strip(), event_id=raw[41:49].strip(),
        ))
    return header, details, trailer


def write_outputs(out_dir: Path, batch_id: str, summary: dict, db: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"summary_{batch_id}.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    rejects = [r for r in db.get("rejects", []) if r.get("batch_id") == batch_id]
    with (out_dir / f"rejects_{batch_id}.dat").open("w") as f:
        for r in rejects:
            f.write(f"R{int(r['seq']):06d}{r.get('account',''):<12}{int(r['sqlcode']):+05d}{r.get('reason','')[:32]:<32}\n")
    locks = [r for r in db.get("pending_locks", []) if r.get("batch_id") == batch_id]
    (out_dir / f"pending_locks_{batch_id}.json").write_text(json.dumps(locks, indent=2, sort_keys=True) + "\n")


def validate_contract(header, details, trailer):
    if header["batch_id"] != trailer["batch_id"]:
        raise ValueError("header/trailer batch mismatch")
    if len(details) != trailer["count"]:
        raise ValueError("trailer count mismatch")
    total = 0
    for d in details:
        if d.seq <= 0 or d.account == "" or d.op not in {"BAL", "RAT", "HLD", "LIM"}:
            raise ValueError("malformed detail record")
        if d.op == "BAL":
            total += d.amount
    if total != trailer["total"]:
        raise ValueError("trailer financial total mismatch")


def apply_detail(db, batch_id: str, d: Detail) -> int:
    dup = ensure_not_duplicate(db, batch_id, d.seq)
    if dup != OK:
        return dup
    if d.op == "BAL":
        code = update_balance(db, d.account, d.amount)
        if code == OK:
            append_ledger(db, batch_id, d.seq, d.account, d.amount, d.event_id)
    elif d.op == "RAT":
        code = update_rate(db, d.account, d.amount)
    elif d.op == "HLD":
        code = update_hold(db, d.account, d.amount)
    elif d.op == "LIM":
        code = update_master_limit(db, d.account, d.amount)
        if code == OK:
            risk_code = update_risk_limit(db, d.account, d.amount)
            if risk_code != OK:
                code = risk_code
    else:
        code = CONSTRAINT
    if code == OK:
        append_audit(db, batch_id, d.seq, d.account, d.op, code, d.event_id)
        mark_applied(db, batch_id, d.seq, d.event_id, d.account, d.op)
    return code


def run(args) -> int:
    out = Path(args.out)
    try:
        header, details, trailer = parse_file(Path(args.input))
        batch_id = args.batch or header["batch_id"]
        validate_contract(header, details, trailer)
    except Exception as exc:
        batch_id = args.batch or "UNKNOWN"
        db = load_db(args.db)
        write_outputs(out, batch_id, {"batch_id": batch_id, "status": "FAILED_CLOSED", "error": str(exc), "applied": 0, "rejected": 0, "skipped": 0}, db)
        return 2
    db = load_db(args.db)
    summary = {"batch_id": batch_id, "applied": 0, "rejected": 0, "skipped": 0, "pending_locks": 0, "status": "OK"}
    for d in details:
        if is_applied(db, batch_id, d.seq):
            summary["skipped"] += 1
            continue
        code = apply_detail(db, batch_id, d)
        if code == OK:
            summary["applied"] += 1
        elif code == DUPLICATE:
            summary["skipped"] += 1
        elif code == LOCK_TIMEOUT:
            holder = db.get("locks", {}).get(d.account, "UNKNOWN")
            append_pending_lock(db, batch_id, d.seq, d.account, holder, d.event_id)
            summary["pending_locks"] += 1
            summary["status"] = "RETRYABLE_LOCK"
            save_db(args.db, db)
            write_outputs(out, batch_id, summary, db)
            return 75
        elif code in {NOT_FOUND, CONSTRAINT}:
            append_reject(db, batch_id, d.seq, d.account, code, "BUSINESS_REJECT", d.event_id)
            summary["rejected"] += 1
        else:
            summary["status"] = "ABEND"
            summary["last_sqlcode"] = code
            save_db(args.db, db)
            write_outputs(out, batch_id, summary, db)
            return 12
        if args.abend_after and summary["applied"] >= args.abend_after:
            summary["status"] = "SIMULATED_ABEND"
            save_db(args.db, db)
            write_outputs(out, batch_id, summary, db)
            return 66
    save_db(args.db, db)
    write_outputs(out, batch_id, summary, db)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="")
    parser.add_argument("--input", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--abend-after", type=int, default=0)
    raise SystemExit(run(parser.parse_args()))

if __name__ == "__main__":
    main()
