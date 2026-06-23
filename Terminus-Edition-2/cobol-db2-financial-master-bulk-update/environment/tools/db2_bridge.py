#!/usr/bin/env python3
"""Thin CLI bridge from COBOL FNBULKUP to db2_financial_sim atomic operations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from db2_financial_sim import (
    CONSTRAINT,
    OK,
    append_audit,
    append_ledger,
    append_pending_lock,
    append_reject,
    clone_db,
    ensure_not_duplicate,
    is_applied,
    load_db,
    mark_applied,
    save_db,
    update_balance,
    update_hold,
    update_master_limit,
    update_rate,
    update_risk_limit,
)


def _write_result(value: str) -> None:
    path = os.environ.get("BRIDGE_RESULT")
    if path:
        Path(path).write_text(value + "\n")
    else:
        sys.stdout.write(value + "\n")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _commit_snapshot(db: dict[str, Any], staged: dict[str, Any]) -> None:
    db.clear()
    db.update(staged)


def apply_detail(
    db: dict[str, Any],
    batch_id: str,
    seq: int,
    account: str,
    op: str,
    amount: int,
    event_id: str,
    *,
    check_duplicate: bool,
    atomic_lim: bool,
) -> int:
    if check_duplicate:
        dup = ensure_not_duplicate(db, batch_id, seq)
        if dup != OK:
            return dup
    if op == "BAL":
        code = update_balance(db, account, amount)
        if code == OK:
            append_ledger(db, batch_id, seq, account, amount, event_id)
    elif op == "RAT":
        code = update_rate(db, account, amount)
    elif op == "HLD":
        code = update_hold(db, account, amount)
    elif op == "LIM":
        if atomic_lim:
            staged = clone_db(db)
            code = update_master_limit(staged, account, amount)
            if code == OK:
                code = update_risk_limit(staged, account, amount)
            if code == OK:
                _commit_snapshot(db, staged)
        else:
            code = update_master_limit(db, account, amount)
            if code == OK:
                risk_code = update_risk_limit(db, account, amount)
                if risk_code != OK:
                    code = risk_code
    else:
        code = CONSTRAINT
    if code == OK:
        append_audit(db, batch_id, seq, account, op, code, event_id)
        mark_applied(db, batch_id, seq, event_id, account, op)
    return code


def write_outputs(
    out_dir: Path,
    batch_id: str,
    summary: dict[str, Any],
    db: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"summary_{batch_id}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    rejects = [r for r in db.get("rejects", []) if r.get("batch_id") == batch_id]
    with (out_dir / f"rejects_{batch_id}.dat").open("w") as handle:
        for reject in rejects:
            seq = int(reject["seq"])
            account = reject.get("account", "")
            sqlcode = int(reject["sqlcode"])
            reason = reject.get("reason", "")[:32]
            handle.write(
                f"R{seq:06d}{account:<12}{sqlcode:+05d}{reason:<32}\n"
            )
    locks = [r for r in db.get("pending_locks", []) if r.get("batch_id") == batch_id]
    (out_dir / f"pending_locks_{batch_id}.json").write_text(
        json.dumps(locks, indent=2, sort_keys=True) + "\n"
    )


def parse_input_header_trailer(input_path: Path) -> tuple[dict[str, str], dict[str, int], int]:
    lines = [
        line.rstrip("\n")
        for line in input_path.read_text().splitlines()
        if line.rstrip("\n")
    ]
    if len(lines) < 2 or not lines[0].startswith("H") or not lines[-1].startswith("T"):
        raise ValueError("missing header or trailer")
    header = {
        "batch_id": lines[0][1:11].strip(),
        "business_date": lines[0][11:19],
        "source": lines[0][19:27].strip(),
    }
    sign = lines[-1][17:18]
    amount = int(lines[-1][18:30])
    if sign == "-":
        amount = -amount
    elif sign != "+":
        raise ValueError("bad signed amount")
    trailer = {
        "batch_id": lines[-1][1:11].strip(),
        "count": int(lines[-1][11:17]),
        "total": amount,
    }
    detail_count = len(lines) - 2
    return header, trailer, detail_count


def load_control(
    control_path: str,
    header: dict[str, str],
    detail_count: int,
    financial_total: int,
    input_path: Path,
) -> tuple[dict[str, Any] | None, str]:
    if not control_path:
        return None, hashlib.sha256(input_path.read_bytes()).hexdigest()
    try:
        control = json.loads(Path(control_path).read_text())
    except Exception as exc:
        raise ValueError(f"malformed control manifest: {exc}") from exc
    expected = {
        "batch_id": header["batch_id"],
        "business_date": header["business_date"],
        "source": header["source"],
        "detail_count": detail_count,
        "financial_total": financial_total,
    }
    if control.get("batch_id") != expected["batch_id"]:
        raise ValueError("control batch id mismatch")
    if control.get("business_date") != expected["business_date"]:
        raise ValueError("control business date mismatch")
    if control.get("source") != expected["source"]:
        raise ValueError("control source mismatch")
    if int(control.get("expected_detail_count", -1)) != expected["detail_count"]:
        raise ValueError("control detail count mismatch")
    if int(control.get("expected_financial_total", -999999999999)) != expected["financial_total"]:
        raise ValueError("control financial total mismatch")
    return control, hashlib.sha256(input_path.read_bytes()).hexdigest()


def enforce_control_replay(db: dict[str, Any], batch_id: str, input_hash: str) -> None:
    entry = db.setdefault("control_totals", {}).get(batch_id)
    if entry and entry.get("input_sha256") != input_hash:
        raise ValueError("duplicate batch id with different input hash")


def record_control_total(
    db: dict[str, Any],
    batch_id: str,
    control: dict[str, Any] | None,
    input_hash: str,
    summary: dict[str, Any],
) -> None:
    if not control:
        return
    status = (
        "SETTLED"
        if summary.get("status") == "OK" and summary.get("pending_locks", 0) == 0
        else summary.get("status", "UNKNOWN")
    )
    db.setdefault("control_totals", {})[batch_id] = {
        "batch_id": batch_id,
        "business_date": control.get("business_date"),
        "source": control.get("source"),
        "detail_count": int(control.get("expected_detail_count", 0)),
        "financial_total": int(control.get("expected_financial_total", 0)),
        "input_sha256": input_hash,
        "status": status,
    }


def cmd_load(_args: argparse.Namespace) -> int:
    load_db(_env("BRIDGE_DB"))
    _write_result("0")
    return 0


def cmd_save(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    save_db(_env("BRIDGE_DB"), db)
    _write_result("0")
    return 0


def cmd_is_applied(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    applied = is_applied(db, _env("BRIDGE_BATCH"), int(_env("BRIDGE_SEQ")))
    _write_result("1" if applied else "0")
    return 0


def cmd_apply_detail(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    flags = {part.strip() for part in _env("BRIDGE_FLAGS", "").split(",") if part.strip()}
    code = apply_detail(
        db,
        _env("BRIDGE_BATCH"),
        int(_env("BRIDGE_SEQ")),
        _env("BRIDGE_ACCOUNT"),
        _env("BRIDGE_OP"),
        int(_env("BRIDGE_AMOUNT")),
        _env("BRIDGE_EVENT_ID"),
        check_duplicate="check-duplicate" in flags,
        atomic_lim="atomic-lim" in flags,
    )
    save_db(_env("BRIDGE_DB"), db)
    _write_result(str(code))
    return 0


def cmd_append_reject(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    append_reject(
        db,
        _env("BRIDGE_BATCH"),
        int(_env("BRIDGE_SEQ")),
        _env("BRIDGE_ACCOUNT"),
        int(_env("BRIDGE_SQLCODE")),
        _env("BRIDGE_REASON", "BUSINESS_REJECT"),
        _env("BRIDGE_EVENT_ID"),
    )
    save_db(_env("BRIDGE_DB"), db)
    _write_result("0")
    return 0


def cmd_append_pending_lock(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    holder = db.get("locks", {}).get(_env("BRIDGE_ACCOUNT"), "UNKNOWN")
    append_pending_lock(
        db,
        _env("BRIDGE_BATCH"),
        int(_env("BRIDGE_SEQ")),
        _env("BRIDGE_ACCOUNT"),
        holder,
        _env("BRIDGE_EVENT_ID"),
    )
    save_db(_env("BRIDGE_DB"), db)
    _write_result("0")
    return 0


def cmd_write_outputs(args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    summary = {
        "batch_id": _env("BRIDGE_BATCH"),
        "applied": int(_env("BRIDGE_APPLIED", "0")),
        "rejected": int(_env("BRIDGE_REJECTED", "0")),
        "skipped": int(_env("BRIDGE_SKIPPED", "0")),
        "status": _env("BRIDGE_STATUS", "OK"),
    }
    pending = _env("BRIDGE_PENDING_LOCKS", "")
    if pending:
        summary["pending_locks"] = int(pending)
    last_sqlcode = _env("BRIDGE_LAST_SQLCODE", "")
    if last_sqlcode:
        summary["last_sqlcode"] = int(last_sqlcode)
    error = _env("BRIDGE_ERROR", "")
    if error:
        summary["error"] = error
    write_outputs(Path(_env("BRIDGE_OUT")), _env("BRIDGE_BATCH"), summary, db)
    _write_result("0")
    return 0


def cmd_failed_closed(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    summary = {
        "batch_id": _env("BRIDGE_BATCH"),
        "status": "FAILED_CLOSED",
        "error": _env("BRIDGE_ERROR", "validation failure"),
        "applied": 0,
        "rejected": 0,
        "skipped": 0,
    }
    write_outputs(Path(_env("BRIDGE_OUT")), _env("BRIDGE_BATCH"), summary, db)
    _write_result("0")
    return 0


def cmd_input_hash(_args: argparse.Namespace) -> int:
    digest = hashlib.sha256(Path(_env("BRIDGE_INPUT")).read_bytes()).hexdigest()
    _write_result(digest)
    return 0


def cmd_validate_control(_args: argparse.Namespace) -> int:
    input_path = Path(_env("BRIDGE_INPUT"))
    header, trailer, detail_count = parse_input_header_trailer(input_path)
    financial_total = trailer["total"]
    load_control(
        _env("BRIDGE_CONTROL", ""),
        header,
        detail_count,
        financial_total,
        input_path,
    )
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    _write_result(digest)
    return 0


def cmd_enforce_control_replay(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    try:
        enforce_control_replay(db, _env("BRIDGE_BATCH"), _env("BRIDGE_INPUT_HASH"))
    except ValueError as exc:
        _write_result(str(exc))
        return 1
    save_db(_env("BRIDGE_DB"), db)
    _write_result("0")
    return 0


def cmd_record_control_total(_args: argparse.Namespace) -> int:
    db = load_db(_env("BRIDGE_DB"))
    control_path = _env("BRIDGE_CONTROL", "")
    control = json.loads(Path(control_path).read_text()) if control_path else None
    summary = {
        "status": _env("BRIDGE_STATUS", "OK"),
        "pending_locks": int(_env("BRIDGE_PENDING_LOCKS", "0")),
    }
    record_control_total(db, _env("BRIDGE_BATCH"), control, _env("BRIDGE_INPUT_HASH"), summary)
    save_db(_env("BRIDGE_DB"), db)
    _write_result("0")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DB2 simulator bridge for FNBULKUP")
    sub = parser.add_subparsers(dest="command", required=True)
    handlers: dict[str, Any] = {}
    for name, handler in [
        ("load", cmd_load),
        ("save", cmd_save),
        ("is-applied", cmd_is_applied),
        ("apply-detail", cmd_apply_detail),
        ("append-reject", cmd_append_reject),
        ("append-pending-lock", cmd_append_pending_lock),
        ("write-outputs", cmd_write_outputs),
        ("failed-closed", cmd_failed_closed),
        ("input-hash", cmd_input_hash),
        ("validate-control", cmd_validate_control),
        ("enforce-control-replay", cmd_enforce_control_replay),
        ("record-control-total", cmd_record_control_total),
    ]:
        handlers[name] = handler
        sub.add_parser(name)
    args = parser.parse_args()
    try:
        return handlers[args.command](args)
    except Exception as exc:
        _write_result(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
