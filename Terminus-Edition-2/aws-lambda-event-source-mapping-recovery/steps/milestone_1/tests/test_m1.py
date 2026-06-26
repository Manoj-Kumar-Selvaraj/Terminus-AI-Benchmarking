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

class TestMilestone1:
    def test_handler_entry_point_not_relocated(self):
        """The production handler must remain at /app/handler/index.mjs."""
        assert (APP / "handler" / "index.mjs").is_file()

    def test_mapping_discovers_enabled_migrated_queue(self, tmp_path):
        """The active event-source mapping must be enabled and point to the migrated queue."""
        result, _ledger, _dlq = run_sim(tmp_path, "mapping")
        queues = load_json(APP / "config" / "queues.json")
        assert result["active"] is True
        assert result["enabled"] is True
        assert result["event_source_arn"] == queues["expected_active_queue_arn"]
        assert result["event_source_arn"] != queues["old_queue_arn"]

    def test_function_alias_batch_size_and_partial_response_contract_are_preserved(self, tmp_path):
        """The mapping must keep the live alias, batch size, and ReportBatchItemFailures contract."""
        result, _ledger, _dlq = run_sim(tmp_path, "mapping")
        queues = load_json(APP / "config" / "queues.json")
        assert result["function_name"] == queues["compatible_function_target"]
        assert result["batch_size"] == 3
        assert "ReportBatchItemFailures" in result["function_response_types"]

    def test_new_queue_batch_is_the_only_active_source_when_mapping_is_probed(self, tmp_path):
        """A new-queue fixture can be delivered only when the mapping source is the migrated queue."""
        result, _ledger, _dlq = run_sim(tmp_path, "batch", APP / "data" / "sqs_batch_01.json", cycles=1)
        assert result["mapping"]["active"] is True
        assert result["queue_arn"] == result["mapping"]["expected_event_source_arn"]

    def test_old_queue_noise_batch_does_not_feed_active_processing(self, tmp_path):
        """Historical old-queue data must not become the active Lambda source."""
        result, ledger, _dlq = run_sim(tmp_path, "batch", APP / "data" / "old_queue_noise_batch.json", cycles=1)
        assert result["queue_arn"] == result["mapping"]["old_queue_arn"]
        assert result["delivered_message_ids"] == []
        assert ledger == []


    def test_mapping_preserves_stable_uuid_and_exact_operational_controls(self):
        """The repaired mapping retains identity and exact concurrency and batching controls."""
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["uuid"] == "esm-payments-ledger-live-20260613"
        assert mapping["maximum_batching_window_seconds"] == 2
        assert mapping["scaling_config"] == {"maximum_concurrency": 4}
        assert mapping["bisect_batch_on_function_error"] is False

    def test_mapping_filter_is_exact_and_response_type_is_not_duplicated(self):
        """Only ledger-credit events are selected and partial failure mode appears once."""
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["filter_criteria"] == {"event_type": ["ledger_credit"]}
        assert mapping["function_response_types"] == ["ReportBatchItemFailures"]

    def test_mapping_target_is_alias_qualified_and_queue_arn_is_nonempty(self):
        """The mapping cannot fall back to an unqualified function or empty queue source."""
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["function_name"].count(":") == 1
        assert mapping["function_name"].endswith(":live")
        assert mapping["event_source_arn"].startswith("arn:aws:sqs:")
