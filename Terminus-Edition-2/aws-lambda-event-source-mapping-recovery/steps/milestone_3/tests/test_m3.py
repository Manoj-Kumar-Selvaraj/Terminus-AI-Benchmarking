import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable
SRC_DIR = APP / "src"
HANDLER_DIR = APP / "handler"

EXPECTED_RUNTIME_HASHES = {
    "src/handler_bridge.py": "43a429376a65c2b156ea3991507f158667878603c3b55e8a785196b0afb792a5",
    "src/iam_simulator.py": "4058f0938e6898516852443a85e287cb6b634b05d81ce6e2549b130b435ef424",
    "src/jsonio.py": "b02f370932d6b3fd79e2b68f548442a6ceaeef9d9755685b7803f0d40edca841",
    "src/mapping.py": "20f85f93420621ebb4c66271102c63308b9a7dfc49affdbe974a3e02a5e33c9a",
    "src/paths.py": "4bc3961286a5f232e3d2a5304c77c835942d6ea2febe8ebd056f541ca39f10d8",
    "src/simulator.py": "9972671cb1630234649ba9687af445da38acc48cb1ec2deabf5b39334bc3b2a0",
    "src/state_store.py": "15e0ea35acc3b2ec2c5f7ea70d8beb6882f09ed2a4e552411a7e3ab7945add7d",
    "handler/invoke.mjs": "e813d6b93639ef16b3a2a4f2fd905bbdaf9c8810e2a50318676d8cbd56fef21d",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def assert_runtime_integrity() -> None:
    """Offline simulator runtime sources must not be rewritten to bypass the handler."""
    for rel_path, expected in EXPECTED_RUNTIME_HASHES.items():
        actual = hashlib.sha256((APP / rel_path).read_bytes()).hexdigest()
        assert actual == expected, f"{rel_path} was modified"


def run_sim(tmp_path, scenario, batch=None, cycles=1):
    assert_runtime_integrity()
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


def invoke_handler_raw(tmp_path, records, env_extra=None):
    assert_runtime_integrity()
    ledger = tmp_path / "handler_ledger.json"
    ledger.write_text("[]\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP)
    env["APP_ROOT"] = str(APP)
    env["SIDE_EFFECT_LEDGER"] = str(ledger)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["node", str(HANDLER_DIR / "invoke.mjs")],
        input=json.dumps({"Records": records}),
        text=True,
        capture_output=True,
        env=env,
        cwd=APP,
    )


def invoke_handler(tmp_path, records):
    proc = invoke_handler_raw(tmp_path, records)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return json.loads(proc.stdout)


class TestMilestone3:
    def test_handler_returns_documented_partial_batch_shape(self, tmp_path):
        """The handler must emit batchItemFailures with only failed message IDs."""
        records = [
            sqs_message("h-good-1", "H-GOOD-1"),
            sqs_message("h-poison-2", "H-POISON-2", poison=True),
            sqs_message("h-good-3", "H-GOOD-3"),
        ]
        response = invoke_handler(tmp_path, records)
        assert "batchItemFailures" in response
        failed = [item["itemIdentifier"] for item in response["batchItemFailures"]]
        assert failed == ["h-poison-2"]
        assert "h-good-1" not in failed
        assert "h-good-3" not in failed

    def test_poison_message_partial_failure_does_not_retry_good_records(self, tmp_path):
        """Only the poison record should fail; successful peers should be committed and deleted once."""
        result, ledger, _dlq = run_sim(tmp_path, "batch", APP / "data" / "sqs_batch_with_poison.json", cycles=2)
        assert len(ledger) == 2
        assert {entry["business_event_id"] for entry in ledger} == {"PAY-2001", "PAY-2003"}
        assert result["failed_message_ids"].count("msg-poison-2002") == 2
        assert "msg-good-2001" not in result["failed_message_ids"]
        assert "msg-good-2003" not in result["failed_message_ids"]
        assert result["deleted_message_ids"].count("msg-good-2001") == 1
        assert result["deleted_message_ids"].count("msg-good-2003") == 1
        assert result["receive_counts"]["msg-poison-2002"] == 2
        assert result["receive_counts"]["msg-good-2001"] == 1
        assert result["receive_counts"]["msg-good-2003"] == 1

    def test_malformed_record_does_not_block_valid_peer(self, tmp_path):
        """Malformed JSON must be returned as a failed item while valid peers still commit."""
        result, ledger, _dlq = run_sim(tmp_path, "batch", APP / "data" / "malformed_and_valid_batch.json", cycles=1)
        assert len(ledger) == 1
        assert {entry["business_event_id"] for entry in ledger} == {"PAY-4002"}
        assert "msg-malformed-4001" in result["failed_message_ids"]
        assert "msg-good-4002" in result["deleted_message_ids"]

    def test_dynamic_partial_batch_response_uses_only_failed_message_ids(self, tmp_path):
        """The partial response contract must work for non-fixture message IDs as well."""
        batch = write_temp_batch(tmp_path, [sqs_message("dyn-good-a", "DYN-A", 11), sqs_message("dyn-poison-b", "DYN-B", poison=True), sqs_message("dyn-good-c", "DYN-C", 13)])
        result, ledger, _dlq = run_sim(tmp_path, "batch", batch, cycles=1)
        assert len(ledger) == 2
        assert {e["business_event_id"] for e in ledger} == {"DYN-A", "DYN-C"}
        assert result["failed_message_ids"] == ["dyn-poison-b"]
        assert set(result["deleted_message_ids"]) == {"dyn-good-a", "dyn-good-c"}

    def test_poison_fixture_was_not_removed_or_neutered(self):
        """The supplied poison fixture must still contain a poison record for the verifier replay."""
        batch = load_json(APP / "data" / "sqs_batch_with_poison.json")
        bodies = [json.loads(m["body"]) for m in batch["messages"]]
        assert any(body.get("poison") is True for body in bodies)
        assert {m["messageId"] for m in batch["messages"]} >= {"msg-good-2001", "msg-poison-2002", "msg-good-2003"}


    def test_empty_batch_returns_exact_empty_partial_response(self, tmp_path):
        """An empty SQS delivery returns the exact partial-batch envelope."""
        response = invoke_handler(tmp_path, [])
        assert response == {"batchItemFailures": []}

    def test_failure_identifiers_are_unique_valid_and_input_ordered(self, tmp_path):
        """Multiple failures are reported once each and retain input order."""
        records = [sqs_message("bad-a", "BAD-A", poison=True), sqs_message("good-b", "GOOD-B"), sqs_message("bad-c", "BAD-C", malformed=True)]
        response = invoke_handler(tmp_path, records)
        ids = [x["itemIdentifier"] for x in response["batchItemFailures"]]
        assert ids == ["bad-a", "bad-c"]
        assert len(ids) == len(set(ids))
        assert set(ids) <= {r["messageId"] for r in records}

    def test_handler_does_not_mutate_inbound_records(self, tmp_path):
        """The handler must leave SQS record bodies, attributes, and identifiers unchanged."""
        records = [
            sqs_message("keep-a", "KEEP-A", amount=21),
            sqs_message("keep-b", "KEEP-B", poison=True),
        ]
        before = copy.deepcopy(records)
        invoke_handler(tmp_path, records)
        assert records == before

    def test_unexpected_handler_error_fails_invocation(self, tmp_path):
        """Unexpected errors must fail the invocation instead of returning a whole-batch retry response."""
        ledger_dir = tmp_path / "ledger-is-a-directory"
        ledger_dir.mkdir()
        proc = invoke_handler_raw(
            tmp_path,
            [sqs_message("good-only", "GOOD-ONLY")],
            env_extra={"SIDE_EFFECT_LEDGER": str(ledger_dir)},
        )
        assert proc.returncode != 0
        assert "batchItemFailures" not in proc.stdout
