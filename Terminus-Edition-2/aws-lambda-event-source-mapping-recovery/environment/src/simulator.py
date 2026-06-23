from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any
from .jsonio import load_json, save_json
from .paths import config_path, ledger_path, dlq_path
from .mapping import active_mapping
from .iam_simulator import required_sqs_decisions, has_broad_sqs_grant, has_log_permissions, decide
from .state_store import load_ledger, load_dlq, append_dlq_entry
from . import handler_bridge

def load_runtime() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return load_json(config_path("event_source_mapping.json")), load_json(config_path("queues.json")), load_json(config_path("lambda_role_policy.json"))

def mapping_probe() -> dict[str, Any]:
    mapping, queues, _policy = load_runtime()
    return active_mapping(mapping, queues)

def iam_probe() -> dict[str, Any]:
    _mapping, queues, policy = load_runtime()
    queue_arn = queues["expected_active_queue_arn"]
    return {"queue_arn": queue_arn, "decisions": required_sqs_decisions(policy, queue_arn), "old_queue_receive": decide(policy, "sqs:ReceiveMessage", queues["old_queue_arn"]), "has_broad_sqs_grant": has_broad_sqs_grant(policy), "has_log_permissions": has_log_permissions(policy)}

def _event_records(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for msg in messages:
        cloned = dict(msg)
        attrs = dict(cloned.get("attributes", {}))
        attrs["ApproximateReceiveCount"] = str(int(attrs.get("ApproximateReceiveCount", "0")) + 1)
        cloned["attributes"] = attrs
        records.append(cloned)
    return records

def _message_reason(message: dict[str, Any]) -> str:
    try:
        body = json.loads(message.get("body", ""))
        if body.get("poison"):
            return body.get("failure_reason", "POISON_MESSAGE")
        return "PROCESSING_FAILED"
    except Exception:
        return "MALFORMED_JSON"

def simulate_batch(batch_file: str | Path, cycles: int = 1) -> dict[str, Any]:
    mapping, queues, policy = load_runtime()
    map_info = active_mapping(mapping, queues)
    batch = load_json(batch_file)
    redrive = load_json(config_path("redrive_policy.json"))
    queue_arn = batch.get("queue_arn", queues["expected_active_queue_arn"])
    result: dict[str, Any] = {"mapping": map_info, "queue_arn": queue_arn, "cycles": [], "access_denied": False, "access_denied_actions": [], "delivered_message_ids": [], "deleted_message_ids": [], "failed_message_ids": [], "receive_counts": {}, "dlq_message_ids": []}
    required = required_sqs_decisions(policy, queues["expected_active_queue_arn"])
    denied = [a for a, d in required.items() if d != "allowed"]
    if denied:
        result["access_denied"] = True
        result["access_denied_actions"] = denied
        result["ledger_entries"] = load_ledger(ledger_path())
        result["dlq_entries"] = load_dlq(dlq_path())
        return result
    if not map_info["active"] or queue_arn != queues["expected_active_queue_arn"]:
        result["ledger_entries"] = load_ledger(ledger_path())
        result["dlq_entries"] = load_dlq(dlq_path())
        return result
    messages = [dict(m) for m in batch.get("messages", [])]
    max_receive = int(redrive.get("max_receive_count", 3))
    deleted: set[str] = set()
    dlqed: set[str] = set()
    for _cycle in range(cycles):
        available = [m for m in messages if m.get("messageId") not in deleted and m.get("messageId") not in dlqed]
        if not available:
            result["cycles"].append({"delivered": [], "failed": [], "deleted": []})
            continue
        delivered = available[:int(mapping.get("batch_size", 10))]
        records = _event_records(delivered)
        for rec, original in zip(records, delivered):
            original.setdefault("attributes", {})["ApproximateReceiveCount"] = rec["attributes"]["ApproximateReceiveCount"]
            result["receive_counts"][original["messageId"]] = int(original["attributes"]["ApproximateReceiveCount"])
        response = handler_bridge.handle_batch({"Records": records})
        failures = response.get("batchItemFailures", []) if isinstance(response, dict) else []
        failed_ids = {item.get("itemIdentifier") for item in failures if isinstance(item, dict)}
        cycle_deleted = []
        cycle_failed = []
        for message in delivered:
            mid = message["messageId"]
            result["delivered_message_ids"].append(mid)
            if mid in failed_ids:
                result["failed_message_ids"].append(mid)
                cycle_failed.append(mid)
                receive_count = int(message.get("attributes", {}).get("ApproximateReceiveCount", "0"))
                if receive_count >= max_receive:
                    body_event_id = None
                    try:
                        body_event_id = json.loads(message.get("body", "{}")).get("business_event_id")
                    except Exception:
                        pass
                    append_dlq_entry(dlq_path(), {"message_id": f"dlq-{mid}", "original_message_id": mid, "business_event_id": body_event_id, "source_queue_arn": queue_arn, "failure_reason": _message_reason(message), "receive_count": receive_count})
                    dlqed.add(mid)
                    result["dlq_message_ids"].append(mid)
            else:
                deleted.add(mid)
                result["deleted_message_ids"].append(mid)
                cycle_deleted.append(mid)
        result["cycles"].append({"delivered": [m["messageId"] for m in delivered], "failed": cycle_failed, "deleted": cycle_deleted})
    result["ledger_entries"] = load_ledger(ledger_path())
    result["dlq_entries"] = load_dlq(dlq_path())
    return result

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["mapping", "iam", "batch"], required=True)
    parser.add_argument("--batch", default="")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--result", default="")
    args = parser.parse_args(argv)
    if args.scenario == "mapping":
        result = mapping_probe()
    elif args.scenario == "iam":
        result = iam_probe()
    else:
        if not args.batch:
            parser.error("--batch is required for batch scenario")
        result = simulate_batch(args.batch, cycles=args.cycles)
    if args.result:
        save_json(args.result, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
