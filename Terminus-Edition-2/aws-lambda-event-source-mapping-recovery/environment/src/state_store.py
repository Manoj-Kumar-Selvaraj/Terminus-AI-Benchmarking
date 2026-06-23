from __future__ import annotations
from typing import Any
from .jsonio import load_json, save_json

def load_ledger(path) -> list[dict[str, Any]]:
    return load_json(path, default=[])

def save_ledger(path, entries: list[dict[str, Any]]) -> None:
    save_json(path, entries)

def append_ledger_entry(path, entry: dict[str, Any]) -> bool:
    entries = load_ledger(path)
    entries.append(entry)
    save_ledger(path, entries)
    return True

def load_dlq(path) -> list[dict[str, Any]]:
    return load_json(path, default=[])

def save_dlq(path, entries: list[dict[str, Any]]) -> None:
    save_json(path, entries)

def append_dlq_entry(path, entry: dict[str, Any]) -> bool:
    entries = load_dlq(path)
    entries.append(entry)
    save_dlq(path, entries)
    return True
