from __future__ import annotations

import re
from typing import Any


def _parse_windows(windows_blob: str) -> list[dict[str, str]]:
    windows: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in windows_blob.splitlines():
        stripped = line.strip()
        if stripped.startswith("- window_id:"):
            if current:
                windows.append(current)
            current = {"window_id": stripped.split(":", 1)[1].strip()}
            continue
        if not current:
            continue
        match = re.match(r"(\w+):\s*\"?([^\"]+)\"?", stripped)
        if match:
            current[match.group(1)] = match.group(2).strip().strip('"')
    if current:
        windows.append(current)
    return windows


def _window_for_timestamp(windows_blob: str, batch_run_ts: str) -> str | None:
    for window in _parse_windows(windows_blob):
        open_ts = window.get("open_ts", "")
        close_ts = window.get("close_ts", "")
        if open_ts and close_ts and open_ts <= batch_run_ts <= close_ts:
            return window["window_id"]
    return None


def active_billing_window(
    configmap: dict[str, Any],
    *,
    batch_run_ts: str | None = None,
) -> tuple[str, str]:
    data = configmap.get("data", {})
    pin_key = data.get("active_window_key", "current_window").strip()
    if pin_key and pin_key in data:
        pinned = data[pin_key].strip()
        if pinned:
            return pinned, "pinned_key"

    windows_blob = data.get("windows.yaml", "")
    if batch_run_ts:
        matched = _window_for_timestamp(windows_blob, batch_run_ts)
        if matched:
            return matched, "timestamp"

    for window in _parse_windows(windows_blob):
        window_id = window.get("window_id")
        if window_id:
            return window_id, "first_listed"
    return "UNKNOWN", "none"


def build_ledger_artifact_name(configmap: dict[str, Any], window_id: str) -> str:
    prefix = configmap.get("data", {}).get("ledger_prefix", "ledger-")
    return f"{prefix}{window_id}"
