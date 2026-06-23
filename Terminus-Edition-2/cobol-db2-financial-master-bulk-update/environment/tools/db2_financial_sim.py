#!/usr/bin/env python3
"""Deterministic offline DB2-style simulator for the financial master task.

The simulator intentionally models only the small subset of DB2 behavior used by
FNBULKUP: row lookup (+100), lock timeout/deadlock (-911), duplicate event
markers (-803), referential/business constraint failures (-530), and committed
side-effect tables. It stores state as JSON so tests and operators can inspect
recovery behavior without real DB2 credentials.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Tuple

OK = 0
NOT_FOUND = 100
LOCK_TIMEOUT = -911
DUPLICATE = -803
CONSTRAINT = -530


def load_db(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with p.open() as f:
        db = json.load(f)
    for key, default in {
        "master": {}, "risk": {}, "locks": {}, "ledger": [], "audit": [],
        "rejects": [], "pending_locks": [], "checkpoint": {}, "applied_events": {},
    }.items():
        db.setdefault(key, copy.deepcopy(default))
    return db


def save_db(path: str | Path, db: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(db, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(p)


def clone_db(db: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(db)


def event_key(batch_id: str, seq: int) -> str:
    return f"{batch_id}|{seq:06d}"


def is_applied(db: Dict[str, Any], batch_id: str, seq: int) -> bool:
    return event_key(batch_id, seq) in db.get("applied_events", {})


def sql_select_master(
    db: Dict[str, Any], account: str
) -> Tuple[int, Dict[str, Any] | None]:
    account = account.strip()
    if account in db.get("locks", {}):
        return LOCK_TIMEOUT, None
    row = db.get("master", {}).get(account)
    if row is None:
        return NOT_FOUND, None
    return OK, row


def ensure_not_duplicate(db: Dict[str, Any], batch_id: str, seq: int) -> int:
    return DUPLICATE if is_applied(db, batch_id, seq) else OK


def update_balance(db: Dict[str, Any], account: str, delta_cents: int) -> int:
    code, row = sql_select_master(db, account)
    if code != OK:
        return code
    row["balance_cents"] = int(row.get("balance_cents", 0)) + int(delta_cents)
    return OK


def update_rate(db: Dict[str, Any], account: str, rate_bp: int) -> int:
    code, row = sql_select_master(db, account)
    if code != OK:
        return code
    if rate_bp < 0 or rate_bp > 3000:
        return CONSTRAINT
    row["rate_bp"] = int(rate_bp)
    return OK


def update_hold(db: Dict[str, Any], account: str, flag_value: int) -> int:
    code, row = sql_select_master(db, account)
    if code != OK:
        return code
    flag = "Y" if int(flag_value) != 0 else "N"
    row["hold_flag"] = flag
    if account in db.get("risk", {}):
        db["risk"][account]["hold_flag"] = flag
    return OK


def update_master_limit(db: Dict[str, Any], account: str, new_limit_cents: int) -> int:
    code, row = sql_select_master(db, account)
    if code != OK:
        return code
    if new_limit_cents < 0:
        return CONSTRAINT
    row["credit_limit_cents"] = int(new_limit_cents)
    return OK


def update_risk_limit(db: Dict[str, Any], account: str, new_limit_cents: int) -> int:
    if account in db.get("locks", {}):
        return LOCK_TIMEOUT
    risk_row = db.get("risk", {}).get(account)
    master_row = db.get("master", {}).get(account)
    if risk_row is None or master_row is None:
        return CONSTRAINT
    if int(new_limit_cents) < int(master_row.get("balance_cents", 0)):
        return CONSTRAINT
    risk_row["exposure_limit_cents"] = int(new_limit_cents)
    return OK


def append_ledger(
    db: Dict[str, Any],
    batch_id: str,
    seq: int,
    account: str,
    delta_cents: int,
    event_id: str,
) -> None:
    db.setdefault("ledger", []).append(
        {
            "batch_id": batch_id,
            "seq": seq,
            "account": account,
            "delta_cents": int(delta_cents),
            "event_id": event_id,
        }
    )


def append_audit(
    db: Dict[str, Any],
    batch_id: str,
    seq: int,
    account: str,
    op: str,
    sqlcode: int,
    event_id: str,
) -> None:
    db.setdefault("audit", []).append(
        {
            "batch_id": batch_id,
            "seq": seq,
            "account": account,
            "op": op,
            "sqlcode": int(sqlcode),
            "event_id": event_id,
        }
    )


def mark_applied(
    db: Dict[str, Any],
    batch_id: str,
    seq: int,
    event_id: str,
    account: str,
    op: str,
) -> None:
    db.setdefault("applied_events", {})[event_key(batch_id, seq)] = {
        "event_id": event_id,
        "account": account,
        "op": op,
    }
    checkpoint = db.setdefault("checkpoint", {})
    checkpoint[batch_id] = max(int(checkpoint.get(batch_id, 0)), int(seq))


def append_reject(
    db: Dict[str, Any],
    batch_id: str,
    seq: int,
    account: str,
    sqlcode: int,
    reason: str,
    event_id: str = "",
) -> None:
    db.setdefault("rejects", []).append(
        {
            "batch_id": batch_id,
            "seq": int(seq),
            "account": account,
            "sqlcode": int(sqlcode),
            "reason": reason,
            "event_id": event_id,
        }
    )


def append_pending_lock(
    db: Dict[str, Any],
    batch_id: str,
    seq: int,
    account: str,
    holder: str,
    event_id: str,
) -> None:
    db.setdefault("pending_locks", []).append(
        {
            "batch_id": batch_id,
            "seq": int(seq),
            "account": account,
            "sqlcode": LOCK_TIMEOUT,
            "lock_holder": holder,
            "event_id": event_id,
        }
    )
