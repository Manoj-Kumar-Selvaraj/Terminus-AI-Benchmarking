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

class TestMilestone5:
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

def invoke_direct(tmp_path, records):
    ledger = tmp_path / "direct-ledger.json"
    ledger.write_text("[]\n", encoding="utf-8")
    env = os.environ.copy()
    env["SIDE_EFFECT_LEDGER"] = str(ledger)
    env["APP_ROOT"] = str(APP)
    proc = subprocess.run(["node", str(APP / "handler" / "invoke.mjs")], input=json.dumps({"Records": records}), text=True, capture_output=True, env=env, cwd=APP)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout), load_json(ledger)

def versioned_message(mid, event_id, version=2, epoch="2026-06-24T09:30:00Z", queue=None, amount=100):
    rec = sqs_message(mid, event_id, amount=amount, queue_arn=queue)
    body = json.loads(rec["body"])
    body["event_version"] = version
    if version == 2:
        body["cutover_epoch"] = epoch
    rec["body"] = json.dumps(body, sort_keys=True)
    return rec

class TestMilestone5Cutover:
    def test_cutover_contract_is_explicit_and_fail_closed(self):
        """The normative cutover configuration pins sources, versions, operation, and epoch."""
        c = load_json(APP / "config" / "cutover_contract.json")
        q = load_json(APP / "config" / "queues.json")
        assert c["active_source_queue_arn"] == q["expected_active_queue_arn"]
        assert c["legacy_source_queue_arn"] == q["old_queue_arn"]
        assert c["accepted_event_versions"] == [1, 2]
        assert c["required_operation"] == "ledger_credit"
        assert c["conflict_policy"] == "FAIL_CLOSED"

    def test_version_one_remains_compatible_on_active_queue(self, tmp_path):
        """A v1 event without an epoch still commits on the migrated queue."""
        response, ledger = invoke_direct(tmp_path, [versioned_message("v1-a", "EV-V1", version=1)])
        assert response == {"batchItemFailures": []}
        assert [x["business_event_id"] for x in ledger] == ["EV-V1"]

    def test_version_two_requires_exact_cutover_epoch(self, tmp_path):
        """A stale v2 epoch fails without blocking a valid v2 sibling."""
        records=[versioned_message("stale-a","EV-STALE",epoch="2026-06-24T09:00:00Z"),versioned_message("fresh-b","EV-FRESH")]
        response, ledger = invoke_direct(tmp_path, records)
        assert response["batchItemFailures"] == [{"itemIdentifier": "stale-a", "failureClassification": "STALE_CUTOVER_EPOCH"}]
        assert [x["business_event_id"] for x in ledger] == ["EV-FRESH"]

    def test_legacy_queue_delivery_is_fenced_even_if_directly_invoked(self, tmp_path):
        """A stale worker cannot bypass the mapping and commit an old-queue record."""
        q=load_json(APP / "config" / "queues.json")
        response, ledger=invoke_direct(tmp_path,[versioned_message("old-a","EV-OLD",queue=q["old_queue_arn"])])
        assert response["batchItemFailures"] == [{"itemIdentifier": "old-a", "failureClassification": "STALE_SOURCE_QUEUE"}]
        assert ledger == []

    def test_unsupported_version_isolated_without_side_effect(self, tmp_path):
        """Unsupported protocols fail closed while valid peers still commit."""
        response, ledger=invoke_direct(tmp_path,[versioned_message("bad-v","EV-BADV",version=3),versioned_message("good-v","EV-GOODV")])
        assert response["batchItemFailures"] == [{"itemIdentifier": "bad-v", "failureClassification": "UNSUPPORTED_EVENT_VERSION"}]
        assert [x["business_event_id"] for x in ledger] == ["EV-GOODV"]

    def test_conflicting_business_event_reuse_fails_without_mutating_commit(self, tmp_path):
        """Same event ID with a different immutable payload is rejected, not deduplicated."""
        first = versioned_message("m-a", "EV-CONFLICT", amount=100)
        second = versioned_message("m-b", "EV-CONFLICT", amount=999)
        response, ledger = invoke_direct(tmp_path, [first, second])
        assert response["batchItemFailures"] == [{"itemIdentifier": "m-b", "failureClassification": "IDEMPOTENCY_CONFLICT"}]
        assert len(ledger)==1 and ledger[0]["amount_cents"]==100
        assert ledger[0].get("duplicate_message_ids",[]) == []

    def test_identical_replay_records_unique_alternate_message_id(self, tmp_path):
        """An identical payload replay remains successful and records unique evidence."""
        first = versioned_message("m-a", "EV-DUPE", amount=100)
        second = versioned_message("m-b", "EV-DUPE", amount=100)
        response, ledger = invoke_direct(tmp_path, [first, second, second])
        assert response == {"batchItemFailures": []}
        assert len(ledger)==1
        assert ledger[0]["duplicate_message_ids"] == ["m-b"]

    def test_non_ledger_credit_operation_is_rejected_without_side_effect(self, tmp_path):
        """Only ledger_credit operations may commit during cutover replay."""
        record = versioned_message("op-bad", "EV-BADOP", amount=100)
        body = json.loads(record["body"])
        body["operation"] = "ledger_debit"
        record["body"] = json.dumps(body, sort_keys=True)
        response, ledger = invoke_direct(tmp_path, [record])
        failure = response["batchItemFailures"][0]
        assert failure["itemIdentifier"] == "op-bad"
        assert failure.get("failureClassification") == "UNSUPPORTED_OPERATION"
        assert ledger == []

    def test_idempotency_conflict_is_classified_without_mutating_commit(self, tmp_path):
        """Conflicting payload reuse is reported as IDEMPOTENCY_CONFLICT and leaves the committed row unchanged."""
        first = versioned_message("m-a", "EV-CONFLICT-CLASS", amount=100)
        second = versioned_message("m-b", "EV-CONFLICT-CLASS", amount=999)
        response, ledger = invoke_direct(tmp_path, [first, second])
        failure = response["batchItemFailures"][0]
        assert failure == {"itemIdentifier": "m-b", "failureClassification": "IDEMPOTENCY_CONFLICT"}
        assert len(ledger) == 1 and ledger[0]["amount_cents"] == 100
