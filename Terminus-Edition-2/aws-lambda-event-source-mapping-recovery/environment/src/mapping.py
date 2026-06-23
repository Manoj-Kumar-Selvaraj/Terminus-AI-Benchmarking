from __future__ import annotations
from typing import Any

def active_mapping(mapping: dict[str, Any], queues: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(mapping.get("enabled"))
    expected_arn = queues.get("expected_active_queue_arn")
    source_arn = mapping.get("event_source_arn")
    active = enabled and source_arn == expected_arn
    return {"uuid": mapping.get("uuid"), "enabled": enabled, "active": active, "function_name": mapping.get("function_name"), "event_source_arn": source_arn, "expected_event_source_arn": expected_arn, "old_queue_arn": queues.get("old_queue_arn"), "batch_size": mapping.get("batch_size"), "function_response_types": mapping.get("function_response_types", [])}
