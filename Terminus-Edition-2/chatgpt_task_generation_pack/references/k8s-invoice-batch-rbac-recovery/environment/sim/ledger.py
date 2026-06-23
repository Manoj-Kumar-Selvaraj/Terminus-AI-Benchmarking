from __future__ import annotations

from typing import Any


def active_billing_window(configmap: dict[str, Any]) -> str:
    windows_blob = configmap.get("data", {}).get("windows.yaml", "")
    for line in windows_blob.splitlines():
        stripped = line.strip()
        if stripped.startswith("- window_id:"):
            return stripped.split(":", 1)[1].strip()
    return "UNKNOWN"


def build_ledger_artifact_name(configmap: dict[str, Any], window_id: str) -> str:
    prefix = configmap.get("data", {}).get("ledger_prefix", "ledger-")
    return f"{prefix}{window_id}"
