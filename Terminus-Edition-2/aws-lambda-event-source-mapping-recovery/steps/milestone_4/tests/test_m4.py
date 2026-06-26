import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable

def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def run_sim(tmp_path, scenario, batch=None, cycles=1):
    ledger = tmp_path / "ledger.json"
    dlq = tmp_path / "dlq.json"
    ledger.write_text("[]\n", encoding="utf-8")
    dlq.write_text("[]\n", encoding="utf-8")
    result = tmp_path / f"{scenario}_result.json"
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", scenario, "--result", str(result)]
    if batch:
        cmd += ["--batch", str(batch), "--cycles", str(cycles)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP)
    env["APP_ROOT"] = str(APP)
    env["SIDE_EFFECT_LEDGER"] = str(ledger)
    env["DLQ_STATE"] = str(dlq)
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(ledger), load_json(dlq)

def write_temp_batch(tmp_path, messages, queue_arn=None):
    queues = load_json(APP / "config" / "queues.json")
    path = tmp_path / "dynamic_batch.json"
    path.write_text(json.dumps({"queue_arn": queue_arn or queues["expected_active_queue_arn"], "messages": messages}, indent=2), encoding="utf-8")
    return path

def sqs_message(mid, event_id, amount=100, account="acct-dyn", poison=False, malformed=False, queue_arn=None):
    queues = load_json(APP / "config" / "queues.json")
    body = {"business_event_id": event_id, "account_id": account, "amount_cents": amount, "currency": "USD", "operation": "ledger_credit"}
    if poison:
        body = {"business_event_id": event_id, "poison": True, "failure_reason": "fixture_poison"}
    rendered = "{bad-json" if malformed else json.dumps(body, sort_keys=True)
    return {"messageId": mid, "receiptHandle": f"rh-{mid}", "eventSourceARN": queue_arn or queues["expected_active_queue_arn"], "body": rendered, "attributes": {"ApproximateReceiveCount": "0"}, "messageAttributes": {}}

def run_sim_with_state(tmp_path, batch, cycles, initial_ledger=None, initial_dlq=None):
    ledger = tmp_path / "ledger.json"
    dlq = tmp_path / "dlq.json"
    ledger.write_text(json.dumps(initial_ledger or [], indent=2), encoding="utf-8")
    dlq.write_text(json.dumps(initial_dlq or [], indent=2), encoding="utf-8")
    result = tmp_path / "result.json"
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", "batch", "--batch", str(batch), "--cycles", str(cycles), "--result", str(result)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP)
    env["APP_ROOT"] = str(APP)
    env["SIDE_EFFECT_LEDGER"] = str(ledger)
    env["DLQ_STATE"] = str(dlq)
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(ledger), load_json(dlq)

class TestMilestone4:
    def test_duplicate_business_event_deliveries_do_not_duplicate_ledger_rows(self, tmp_path):
        """Duplicate SQS messages for the same business event must produce one committed side effect."""
        _result, ledger, _dlq = run_sim_with_state(tmp_path, APP / "data" / "duplicate_delivery_replay.json", cycles=1)
        ids = [entry["business_event_id"] for entry in ledger]
        assert ids.count("PAY-3001") == 1
        assert ids.count("PAY-3002") == 1

        entry = next(item for item in ledger if item["business_event_id"] == "PAY-3001")
        assert "duplicate_message_ids" in entry
        evidence = entry["duplicate_message_ids"]
        primary = entry["message_id"]
        alternate = "msg-replay-3001-b" if primary == "msg-replay-3001-a" else "msg-replay-3001-a"
        assert alternate in evidence

    def test_restart_replay_preserves_preexisting_committed_state(self, tmp_path):
        """Rerunning with an existing committed ledger must not append duplicate business events."""
        initial = [{"message_id": "preexisting-msg", "business_event_id": "PAY-3001", "account_id": "acct-300", "amount_cents": 775, "currency": "USD", "operation": "ledger_credit", "status": "COMMITTED"}]
        _result, ledger, _dlq = run_sim_with_state(tmp_path, APP / "data" / "duplicate_delivery_replay.json", cycles=2, initial_ledger=initial)
        ids = [entry["business_event_id"] for entry in ledger]
        assert ids.count("PAY-3001") == 1
        assert ids.count("PAY-3002") == 1
        assert any(entry["message_id"] == "preexisting-msg" for entry in ledger)

    def test_poison_message_moves_to_dlq_after_max_receives_and_stops_looping(self, tmp_path):
        """A poison message must route to DLQ after max_receive_count and not be delivered afterward."""
        result, _ledger, dlq = run_sim_with_state(tmp_path, APP / "data" / "duplicate_delivery_replay.json", cycles=5)
        redrive = load_json(APP / "config" / "redrive_policy.json")
        poison_id = "msg-poison-3003"
        assert result["receive_counts"][poison_id] == redrive["max_receive_count"]
        assert result["delivered_message_ids"].count(poison_id) == redrive["max_receive_count"]
        assert len([entry for entry in dlq if entry["original_message_id"] == poison_id]) == 1

    def test_dlq_entry_contains_original_id_event_id_source_receive_count_and_reason(self, tmp_path):
        """DLQ entries must preserve stable failure evidence for operations."""
        _result, _ledger, dlq = run_sim_with_state(tmp_path, APP / "data" / "duplicate_delivery_replay.json", cycles=4)
        entry = next(item for item in dlq if item["original_message_id"] == "msg-poison-3003")
        queues = load_json(APP / "config" / "queues.json")
        redrive = load_json(APP / "config" / "redrive_policy.json")
        assert entry["business_event_id"] == "PAY-POISON-3003"
        assert entry["source_queue_arn"] == queues["expected_active_queue_arn"]
        assert entry["receive_count"] == redrive["max_receive_count"]
        assert entry["failure_reason"]

    def test_malformed_message_also_redrives_with_stable_reason(self, tmp_path):
        """Malformed messages should not loop forever and should preserve a stable DLQ reason."""
        batch = write_temp_batch(tmp_path, [sqs_message("dyn-malformed-z", "DYN-Z", malformed=True)])
        _result, _ledger, dlq = run_sim_with_state(tmp_path, batch, cycles=4)
        assert len(dlq) == 1
        assert dlq[0]["original_message_id"] == "dyn-malformed-z"
        assert dlq[0]["failure_reason"] == "MALFORMED_JSON"


    def test_duplicate_message_evidence_is_unique_and_excludes_primary(self, tmp_path):
        """Repeated duplicate deliveries do not grow duplicate evidence with repeated IDs."""
        _result, ledger, _dlq = run_sim_with_state(tmp_path, APP / "data" / "duplicate_delivery_replay.json", cycles=3)
        entry = next(x for x in ledger if x["business_event_id"] == "PAY-3001")
        evidence = entry.get("duplicate_message_ids", [])
        assert len(evidence) == len(set(evidence))
        assert entry["message_id"] not in evidence
        assert set(evidence) == {"msg-replay-3001-a", "msg-replay-3001-b"} - {entry["message_id"]}

    def test_duplicate_message_ids_follow_first_seen_delivery_order(self, tmp_path):
        """Alternate message IDs are recorded in first-seen delivery order."""
        first_batch = write_temp_batch(
            tmp_path,
            [
                sqs_message("msg-order-secondary", "PAY-ORDER-A", amount=50),
                sqs_message("msg-order-primary", "PAY-ORDER-A", amount=50),
            ],
        )
        _result, ledger, _dlq = run_sim_with_state(tmp_path, first_batch, cycles=1)
        entry = next(item for item in ledger if item["business_event_id"] == "PAY-ORDER-A")
        assert entry["message_id"] == "msg-order-secondary"
        assert entry["duplicate_message_ids"] == ["msg-order-primary"]

        second_batch = write_temp_batch(
            tmp_path,
            [
                sqs_message("msg-order2-primary", "PAY-ORDER-B", amount=60),
                sqs_message("msg-order2-secondary", "PAY-ORDER-B", amount=60),
            ],
        )
        _result2, ledger2, _dlq2 = run_sim_with_state(tmp_path, second_batch, cycles=1)
        entry2 = next(item for item in ledger2 if item["business_event_id"] == "PAY-ORDER-B")
        assert entry2["message_id"] == "msg-order2-primary"
        assert entry2["duplicate_message_ids"] == ["msg-order2-secondary"]

    def test_preexisting_dlq_record_prevents_redelivery_and_duplicate_append(self, tmp_path):
        """A message already in durable DLQ state must not be delivered or appended again after restart."""
        queues = load_json(APP / "config" / "queues.json")
        redrive = load_json(APP / "config" / "redrive_policy.json")
        poison_id = "msg-poison-3003"
        initial_dlq = [
            {
                "message_id": "dlq-preexisting",
                "original_message_id": poison_id,
                "business_event_id": "PAY-POISON-3003",
                "source_queue_arn": queues["expected_active_queue_arn"],
                "failure_reason": "schema_missing_amount",
                "receive_count": redrive["max_receive_count"],
            }
        ]
        result, _ledger, dlq = run_sim_with_state(
            tmp_path,
            APP / "data" / "duplicate_delivery_replay.json",
            cycles=3,
            initial_dlq=initial_dlq,
        )
        assert poison_id not in result["delivered_message_ids"]
        assert len([entry for entry in dlq if entry["original_message_id"] == poison_id]) == 1

