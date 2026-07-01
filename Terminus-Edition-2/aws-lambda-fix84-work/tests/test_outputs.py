# ruff: noqa: E402, F811
# ---- from test_m1.py ----
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reconcile(root=APP):
    env = os.environ.copy()
    env["APP_ROOT"] = str(root)
    proc = subprocess.run(
        ["node", str(root / "control_plane" / "reconcile.mjs")],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def run_sim(tmp_path, scenario, batch=None, cycles=1):
    ledger = tmp_path / f"{scenario}-ledger.json"
    dlq = tmp_path / f"{scenario}-dlq.json"
    delivery = tmp_path / f"{scenario}-delivery.json"
    ledger.write_text("[]\n", encoding="utf-8")
    dlq.write_text("[]\n", encoding="utf-8")
    delivery.write_text('{"receive_counts":{},"retired":{}}\n', encoding="utf-8")
    result = tmp_path / f"{scenario}-result.json"
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", scenario, "--result", str(result)]
    if batch:
        cmd += ["--batch", str(batch), "--cycles", str(cycles)]
    env = os.environ.copy()
    env.update({
        "APP_ROOT": str(APP),
        "SIDE_EFFECT_LEDGER": str(ledger),
        "DLQ_STATE": str(dlq),
        "DELIVERY_STATE": str(delivery),
    })
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(ledger), load_json(dlq)


def clone_controller(tmp_path):
    root = tmp_path / "app"
    shutil.copytree(APP / "control_plane", root / "control_plane")
    shutil.copytree(APP / "config", root / "config")
    return root


class TestMapping:
    def test_handler_entry_point_not_relocated(self):
        """Ensures the documented Lambda handler path is a loadable module with a callable handler export."""
        handler_path = APP / "handler" / "index.mjs"
        assert handler_path.is_file()
        proc = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                f"const mod = await import({json.dumps(handler_path.as_uri())});"
                "if (typeof mod.handler !== 'function') process.exit(42);",
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout

    def test_mapping_discovers_enabled_migrated_queue(self, tmp_path):
        """Verifies reconciliation discovers the enabled migrated source queue from runtime configuration."""
        result, _, _ = run_sim(tmp_path, "mapping")
        queues = load_json(APP / "config" / "queues.json")
        assert result["active"] is True
        assert result["enabled"] is True
        assert result["event_source_arn"] == queues["expected_active_queue_arn"]
        assert result["event_source_arn"] != queues["old_queue_arn"]

    def test_function_alias_batch_size_and_partial_response_contract_are_preserved(self, tmp_path):
        """Checks alias, batch size, and partial batch response settings survive mapping recovery."""
        result, _, _ = run_sim(tmp_path, "mapping")
        queues = load_json(APP / "config" / "queues.json")
        assert result["function_name"] == queues["compatible_function_target"]
        assert result["batch_size"] == 3
        assert result["function_response_types"] == ["ReportBatchItemFailures"]

    def test_old_queue_noise_batch_does_not_feed_active_processing(self, tmp_path):
        """Confirms messages from the old source queue are not routed into active processing."""
        result, ledger, _ = run_sim(tmp_path, "batch", APP / "data" / "old_queue_noise_batch.json")
        assert result["queue_arn"] == result["mapping"]["old_queue_arn"]
        assert result["delivered_message_ids"] == []
        assert ledger == []

    def test_mapping_preserves_exact_operational_controls(self):
        """Ensures operational mapping controls are preserved instead of broadened or reset."""
        reconcile()
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["uuid"] == "esm-payments-ledger-live-20260613"
        assert mapping["maximum_batching_window_seconds"] == 2
        assert mapping["scaling_config"] == {"maximum_concurrency": 4}
        assert mapping["bisect_batch_on_function_error"] is False
        assert mapping["filter_criteria"] == {"event_type": ["ledger_credit"]}
        assert mapping["source_access_configurations"] == []

    def test_mapping_target_is_qualified_and_source_is_nonempty(self):
        """Validates the mapping targets a qualified function alias and nonempty source queue."""
        reconcile()
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["function_name"] == "payments-ledger-ingestor:live"
        assert mapping["event_source_arn"].startswith("arn:aws:sqs:")

    def test_deleted_generated_mapping_is_recreated_by_normal_command(self, tmp_path):
        """Proves generated mapping artifacts are recreated by the normal reconciliation command."""
        generated = APP / "config" / "event_source_mapping.json"
        generated.unlink(missing_ok=True)
        result, _, _ = run_sim(tmp_path, "mapping")
        assert generated.is_file()
        assert result["active"] is True

    def test_manual_generated_artifact_edit_is_not_a_false_repair(self, tmp_path):
        """Rejects manual edits to generated artifacts as a substitute for fixing reconciliation."""
        reconcile()
        generated = APP / "config" / "event_source_mapping.json"
        generated.write_text('{"enabled": false, "event_source_arn": "manual"}\n', encoding="utf-8")
        result, _, _ = run_sim(tmp_path, "mapping")
        assert result["active"] is True
        assert load_json(generated)["event_source_arn"] == load_json(APP / "config" / "queues.json")["expected_active_queue_arn"]

    def test_reconciliation_is_byte_stable(self):
        """Checks repeated reconciliation produces byte-stable generated mapping output."""
        reconcile()
        generated = APP / "config" / "event_source_mapping.json"
        first = generated.read_bytes()
        reconcile()
        second = generated.read_bytes()
        assert first == second

    def test_older_rollback_pending_checkpoint_cannot_override_completed_promotion(self, tmp_path):
        """Ensures stale rollback-pending checkpoints cannot override a completed cutover."""
        root = clone_controller(tmp_path)
        checkpoint = load_json(root / "control_plane" / "rollout_checkpoint.json")
        checkpoint["generation"] = 999
        checkpoint["phase"] = "rollback_pending"
        (root / "control_plane" / "rollout_checkpoint.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
        reconcile(root)
        mapping = load_json(root / "config" / "event_source_mapping.json")
        queues = load_json(root / "config" / "queues.json")
        assert mapping["enabled"] is True
        assert mapping["event_source_arn"] == queues["expected_active_queue_arn"]

    def test_queue_reference_is_data_driven_in_isolated_workspace(self, tmp_path):
        """Verifies queue selection follows copied runtime configuration instead of hardcoded ARNs."""
        root = clone_controller(tmp_path)
        queues_path = root / "config" / "queues.json"
        queues = load_json(queues_path)
        replacement = "arn:aws:sqs:eu-west-1:444455556666:payments-ledger-blue"
        queues["expected_active_queue_arn"] = replacement
        queues_path.write_text(json.dumps(queues, indent=2) + "\n")
        reconcile(root)
        assert load_json(root / "config" / "event_source_mapping.json")["event_source_arn"] == replacement

    def test_reconciliation_does_not_duplicate_response_types(self):
        """Ensures response type declarations are not duplicated across repeated reconciliation."""
        reconcile()
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["function_response_types"].count("ReportBatchItemFailures") == 1


# ---- from test_m2.py ----
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable
REQUIRED = [
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:ChangeMessageVisibility",
    "sqs:GetQueueAttributes",
]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reconcile(root=APP):
    env = os.environ.copy()
    env["APP_ROOT"] = str(root)
    proc = subprocess.run(["node", str(root / "control_plane" / "reconcile.mjs")], cwd=root, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout


def run_sim(tmp_path, scenario, batch=None, cycles=1):
    ledger, dlq, delivery = tmp_path / "ledger.json", tmp_path / "dlq.json", tmp_path / "delivery.json"
    ledger.write_text("[]\n")
    dlq.write_text("[]\n")
    delivery.write_text('{"receive_counts":{},"retired":{}}\n')
    result = tmp_path / "result.json"
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", scenario, "--result", str(result)]
    if batch:
        cmd += ["--batch", str(batch), "--cycles", str(cycles)]
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(ledger), "DLQ_STATE": str(dlq), "DELIVERY_STATE": str(delivery)})
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(ledger), load_json(dlq)


def resources(statement):
    value = statement.get("Resource", [])
    return value if isinstance(value, list) else [value]


def actions(statement):
    value = statement.get("Action", [])
    return value if isinstance(value, list) else [value]


def clone_controller(tmp_path):
    root = tmp_path / "app"
    shutil.copytree(APP / "control_plane", root / "control_plane")
    shutil.copytree(APP / "config", root / "config")
    return root


class TestIam:
    def test_iam_evaluator_source_not_tampered(self):
        """Ensures the IAM evaluator used by the verifier has not been modified."""
        expected = "e2bb5dc987e3e1ef95ad21f9664559970587cd2a9466fdcac7ed262c1a8a74e2"
        assert hashlib.sha256((APP / "simulator" / "iam.go").read_bytes()).hexdigest() == expected

    def test_policy_has_one_exact_migrated_queue_statement(self):
        """Checks the rendered policy has one scoped statement for the migrated queue."""
        reconcile()
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        sqs = [s for s in policy["Statement"] if any(str(a).startswith("sqs:") for a in actions(s))]
        assert len(sqs) == 1
        statement = sqs[0]
        assert statement["Effect"] == "Allow"
        assert set(actions(statement)) == set(REQUIRED)
        assert len(actions(statement)) == len(REQUIRED)
        assert resources(statement) == [queues["expected_active_queue_arn"]]

    def test_required_sqs_actions_are_effectively_allowed(self, tmp_path):
        """Verifies all required SQS actions are allowed for the active source queue."""
        result, _, _ = run_sim(tmp_path, "iam")
        assert result["decisions"] == {action: "allowed" for action in REQUIRED}
        assert result["old_queue_receive"] != "allowed"

    def test_mapping_controls_are_preserved_from_prior_recovery(self, tmp_path):
        """Ensures mapping source, batching, filters, and response controls remain recovered."""
        result, _, _ = run_sim(tmp_path, "mapping")
        queues = load_json(APP / "config" / "queues.json")
        assert result["active"] is True
        assert result["event_source_arn"] == queues["expected_active_queue_arn"]
        mapping = load_json(APP / "config" / "event_source_mapping.json")
        assert mapping["batch_size"] == 3
        assert mapping["maximum_batching_window_seconds"] == 2
        assert mapping["function_response_types"] == ["ReportBatchItemFailures"]
        assert mapping["bisect_batch_on_function_error"] is False
        assert mapping["filter_criteria"] == {"event_type": ["ledger_credit"]}

    def test_queue_permissions_are_not_wildcard_broadened(self, tmp_path):
        """Rejects queue permissions broadened to wildcard resources or actions."""
        result, _, _ = run_sim(tmp_path, "iam")
        assert result["has_broad_sqs_grant"] is False
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        for statement in policy["Statement"]:
            if any(str(a).startswith("sqs:") or a == "*" for a in actions(statement)):
                assert "*" not in actions(statement)
                assert "sqs:*" not in actions(statement)
                assert "*" not in resources(statement)

    def test_log_permissions_are_preserved(self, tmp_path):
        """Ensures CloudWatch logging permissions remain available after queue policy repair."""
        result, _, _ = run_sim(tmp_path, "iam")
        assert result["has_log_permissions"] is True
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        flattened = {a for s in policy["Statement"] if s.get("Effect") == "Allow" for a in actions(s)}
        assert {"logs:CreateLogStream", "logs:PutLogEvents"} <= flattened

    def test_batch_simulation_has_no_queue_access_denied(self, tmp_path):
        """Runs the batch simulator to confirm queue access is no longer denied."""
        result, _, _ = run_sim(tmp_path, "batch", APP / "data" / "sqs_batch_01.json")
        assert result["access_denied"] is False
        assert result["access_denied_actions"] == []
        assert result["delivered_message_ids"]

    def test_policy_avoids_notaction_notresource_and_mixed_resources(self):
        """Rejects risky IAM shapes such as NotAction, NotResource, or mixed queue resources."""
        reconcile()
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        for statement in policy["Statement"]:
            assert "NotAction" not in statement
            assert "NotResource" not in statement
            rs = resources(statement)
            assert not ({queues["old_queue_arn"], queues["expected_active_queue_arn"]} <= set(rs))

    def test_manual_generated_policy_edit_is_overwritten_by_synthesis(self, tmp_path):
        """Proves manual generated-policy edits are overwritten by policy synthesis."""
        generated = APP / "config" / "lambda_role_policy.json"
        generated.write_text('{"Version":"2012-10-17","Statement":[]}\n')
        result, _, _ = run_sim(tmp_path, "iam")
        assert result["decisions"] == {action: "allowed" for action in REQUIRED}

    def test_policy_rendering_is_byte_stable_and_non_accumulating(self):
        """Checks policy rendering is stable and does not accumulate duplicate statements."""
        reconcile()
        path = APP / "config" / "lambda_role_policy.json"
        first = path.read_bytes()
        reconcile()
        second = path.read_bytes()
        assert first == second
        policy = load_json(path)
        assert len(policy["Statement"]) == len({json.dumps(s, sort_keys=True) for s in policy["Statement"]})

    def test_active_queue_resource_is_data_driven(self, tmp_path):
        """Verifies the active queue resource follows copied runtime configuration."""
        root = clone_controller(tmp_path)
        queues_path = root / "config" / "queues.json"
        queues = load_json(queues_path)
        replacement = "arn:aws:sqs:ap-south-1:777788889999:payments-ledger-green"
        queues["expected_active_queue_arn"] = replacement
        queues_path.write_text(json.dumps(queues, indent=2) + "\n")
        reconcile(root)
        policy = load_json(root / "config" / "lambda_role_policy.json")
        sqs = [s for s in policy["Statement"] if any(str(a).startswith("sqs:") for a in actions(s))]
        assert len(sqs) == 1 and resources(sqs[0]) == [replacement]

    def test_unrelated_base_explicit_deny_survives_rendering(self, tmp_path):
        """Ensures unrelated explicit deny statements are preserved during rendering."""
        root = clone_controller(tmp_path)
        base_path = root / "control_plane" / "policy_base.json"
        base = load_json(base_path)
        deny = {"Sid": "DenyQuarantineQueue", "Effect": "Deny", "Action": "sqs:ReceiveMessage", "Resource": "arn:aws:sqs:us-east-1:111122223333:quarantine"}
        base["Statement"].append(deny)
        base_path.write_text(json.dumps(base, indent=2) + "\n")
        reconcile(root)
        assert deny in load_json(root / "config" / "lambda_role_policy.json")["Statement"]

    def test_stale_old_queue_grant_is_not_rendered(self):
        """Confirms stale grants for the old queue are not rendered into the active policy."""
        reconcile()
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert all(queues["old_queue_arn"] not in resources(s) for s in policy["Statement"])


# ---- from test_m3.py ----
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sqs_message_m3(mid, event_id, *, amount=100, poison=False, malformed=False, delay=0, infra=False):
    queue = load_json(APP / "config" / "queues.json")["expected_active_queue_arn"]
    body = {"business_event_id": event_id, "account_id": "acct-dyn", "amount_cents": amount, "currency": "USD", "operation": "ledger_credit"}
    if poison:
        body = {"business_event_id": event_id, "poison": True, "failure_reason": "fixture_poison"}
    if delay:
        body["fixture_delay_ms"] = delay
    if infra:
        body["fixture_infrastructure_failure"] = True
    rendered = "{bad-json" if malformed else json.dumps(body, sort_keys=True)
    return {"messageId": mid, "receiptHandle": f"rh-{mid}", "eventSourceARN": queue, "body": rendered, "attributes": {"ApproximateReceiveCount": "0"}, "messageAttributes": {}}


def write_batch_m3(tmp_path, records):
    queue = load_json(APP / "config" / "queues.json")["expected_active_queue_arn"]
    path = tmp_path / "batch.json"
    path.write_text(json.dumps({"queue_arn": queue, "messages": records}, indent=2) + "\n")
    return path


def run_sim_m3(tmp_path, batch, cycles=1):
    ledger, dlq, delivery = tmp_path / "ledger.json", tmp_path / "dlq.json", tmp_path / "delivery.json"
    ledger.write_text("[]\n")
    dlq.write_text("[]\n")
    delivery.write_text('{"receive_counts":{},"retired":{}}\n')
    result = tmp_path / "result.json"
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(ledger), "DLQ_STATE": str(dlq), "DELIVERY_STATE": str(delivery)})
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", "batch", "--batch", str(batch), "--cycles", str(cycles), "--result", str(result)]
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(ledger), load_json(dlq)


def invoke_direct(tmp_path, records, *, ledger_name="direct-ledger.json", extra_env=None, check=True, capture=False):
    ledger = tmp_path / ledger_name
    if not ledger.exists():
        ledger.write_text("[]\n")
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(ledger)})
    capture_path = tmp_path / "captured.json"
    if capture:
        env["POST_HANDLER_RECORDS_PATH"] = str(capture_path)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(["node", str(APP / "handler" / "invoke.mjs")], input=json.dumps({"Records": records}), text=True, capture_output=True, env=env, cwd=APP)
    if check:
        assert proc.returncode == 0, proc.stderr + proc.stdout
    response = json.loads(proc.stdout) if proc.returncode == 0 else None
    captured = load_json(capture_path) if capture and capture_path.exists() else None
    return proc, response, load_json(ledger), captured


class TestBatch:
    def test_harness_entrypoints_are_unchanged(self):
        """Ensures trusted handler and simulator entry points are not modified."""
        assert hashlib.sha256((APP / "handler" / "invoke.mjs").read_bytes()).hexdigest() == "393e1f1d2a4a3859574e928c84c0d61ca14bf86465a0a9678302e1f5e9cee400"
        assert hashlib.sha256((APP / "scripts" / "run_simulation.py").read_bytes()).hexdigest() == "b6441b2798c31d4ce24d65594c332bf98547515698a7a39a5183c7c4ec5452b1"

    def test_prior_mapping_and_iam_recovery_are_preserved(self, tmp_path):
        """Ensures mapping controls and IAM synthesis still work before batch handling."""
        result = tmp_path / "mapping.json"
        proc = subprocess.run(
            [
                PYTHON,
                str(APP / "scripts" / "run_simulation.py"),
                "--scenario",
                "mapping",
                "--result",
                str(result),
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        mapping = load_json(result)
        queues = load_json(APP / "config" / "queues.json")
        assert mapping["event_source_arn"] == queues["expected_active_queue_arn"]
        assert mapping["function_response_types"] == ["ReportBatchItemFailures"]
        generated = load_json(APP / "config" / "event_source_mapping.json")
        assert generated["batch_size"] == 3
        assert generated["maximum_batching_window_seconds"] == 2
        assert generated["bisect_batch_on_function_error"] is False

        iam_result = tmp_path / "iam.json"
        proc = subprocess.run(
            [
                PYTHON,
                str(APP / "scripts" / "run_simulation.py"),
                "--scenario",
                "iam",
                "--result",
                str(iam_result),
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        iam = load_json(iam_result)
        required = {
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:ChangeMessageVisibility",
            "sqs:GetQueueAttributes",
        }
        assert iam["decisions"] == {action: "allowed" for action in required}
        assert iam["old_queue_receive"] != "allowed"

    def test_handler_returns_documented_partial_batch_shape(self, tmp_path):
        """Verifies the handler returns the documented partial batch response shape."""
        records = [sqs_message_m3("ok-1", "EV-1"), sqs_message_m3("bad-2", "EV-2", poison=True)]
        _, response, _, _ = invoke_direct(tmp_path, records)
        assert list(response) == ["batchItemFailures"]
        assert response["batchItemFailures"] == [{"itemIdentifier": "bad-2"}]

    def test_poison_message_does_not_retry_good_peers(self, tmp_path):
        """Confirms poison messages fail without retrying successful peers."""
        result, ledger, _ = run_sim_m3(tmp_path, APP / "data" / "sqs_batch_with_poison.json")
        assert result["failed_message_ids"] == ["msg-poison-2002"]
        assert result["deleted_message_ids"] == ["msg-good-2001", "msg-good-2003"]
        assert {row["business_event_id"] for row in ledger} == {"PAY-2001", "PAY-2003"}

    def test_malformed_record_does_not_block_valid_peer(self, tmp_path):
        """Ensures malformed JSON records do not block valid records in the same batch."""
        result, ledger, _ = run_sim_m3(tmp_path, APP / "data" / "malformed_and_valid_batch.json")
        assert result["failed_message_ids"] == ["msg-malformed-4001"]
        assert result["deleted_message_ids"] == ["msg-good-4002"]
        assert [row["business_event_id"] for row in ledger] == ["PAY-4002"]

    def test_schema_invalid_record_does_not_block_valid_peer(self, tmp_path):
        """Ensures schema-invalid JSON records do not block valid records in the same batch."""
        invalid = sqs_message_m3("schema-bad", "SCHEMA-BAD")
        body = json.loads(invalid["body"])
        del body["account_id"]
        invalid["body"] = json.dumps(body, sort_keys=True)
        records = [invalid, sqs_message_m3("schema-good", "SCHEMA-GOOD")]
        _, response, ledger, _ = invoke_direct(tmp_path, records)
        assert response == {"batchItemFailures": [{"itemIdentifier": "schema-bad"}]}
        assert [row["business_event_id"] for row in ledger] == ["SCHEMA-GOOD"]

    def test_dynamic_partial_response_uses_only_failed_ids(self, tmp_path):
        """Checks partial responses include only the failed message identifiers."""
        records = [sqs_message_m3("dyn-good-a", "DYN-A"), sqs_message_m3("dyn-poison-b", "DYN-B", poison=True), sqs_message_m3("dyn-good-c", "DYN-C")]
        _, response, ledger, _ = invoke_direct(tmp_path, records)
        assert response == {"batchItemFailures": [{"itemIdentifier": "dyn-poison-b"}]}
        assert {row["business_event_id"] for row in ledger} == {"DYN-A", "DYN-C"}

    def test_poison_and_malformed_fixtures_remain_present(self):
        """Confirms poison and malformed fixture coverage remains present."""
        poison = load_json(APP / "data" / "sqs_batch_with_poison.json")
        assert any(json.loads(m["body"]).get("poison") is True for m in poison["messages"])
        malformed = load_json(APP / "data" / "malformed_and_valid_batch.json")
        assert any(m["body"] == "{not-json" for m in malformed["messages"])

    def test_empty_batch_returns_exact_empty_response(self, tmp_path):
        """Verifies an empty event returns the exact empty partial-batch response."""
        _, response, ledger, _ = invoke_direct(tmp_path, [])
        assert response == {"batchItemFailures": []}
        assert ledger == []

    def test_failure_identifiers_are_unique_valid_and_input_ordered(self, tmp_path):
        """Ensures failure identifiers are unique, valid, and ordered by input position."""
        records = [
            sqs_message_m3("fail-z", "E1", poison=True, delay=80),
            sqs_message_m3("ok-y", "E2", delay=20),
            sqs_message_m3("fail-x", "E3", malformed=True),
            sqs_message_m3("fail-z", "E4", poison=True),
        ]
        _, response, _, _ = invoke_direct(tmp_path, records)
        assert response["batchItemFailures"] == [{"itemIdentifier": "fail-z"}, {"itemIdentifier": "fail-x"}]

    def test_asynchronous_completion_does_not_reorder_failures(self, tmp_path):
        """Checks asynchronous processing does not reorder failed item identifiers."""
        records = [
            sqs_message_m3("slow-first", "E-SLOW", poison=True, delay=120),
            sqs_message_m3("fast-second", "E-FAST", poison=True, delay=1),
            sqs_message_m3("mid-third", "E-MID", poison=True, delay=50),
        ]
        _, response, _, _ = invoke_direct(tmp_path, records)
        assert [x["itemIdentifier"] for x in response["batchItemFailures"]] == ["slow-first", "fast-second", "mid-third"]

    def test_slow_successes_around_failure_commit_once(self, tmp_path):
        """Verifies slow successful records around a failure commit exactly once."""
        records = [sqs_message_m3("slow-a", "EV-A", delay=100), sqs_message_m3("bad-b", "EV-B", poison=True), sqs_message_m3("fast-c", "EV-C", delay=1)]
        _, response, ledger, _ = invoke_direct(tmp_path, records)
        assert response == {"batchItemFailures": [{"itemIdentifier": "bad-b"}]}
        assert sorted(row["business_event_id"] for row in ledger) == ["EV-A", "EV-C"]

    def test_handler_does_not_mutate_inbound_records_or_nested_values(self, tmp_path):
        """Ensures the handler does not mutate inbound records or nested attributes."""
        records = [sqs_message_m3("immut-a", "IMM-A")]
        records[0]["messageAttributes"] = {"nested": {"stringValue": "keep"}}
        original = json.loads(json.dumps(records))
        _, _, _, captured = invoke_direct(tmp_path, records, capture=True)
        assert captured == original

    def test_unexpected_infrastructure_error_fails_invocation(self, tmp_path):
        """Confirms unexpected infrastructure failures fail the whole invocation without bad side effects."""
        proc, response, ledger, _ = invoke_direct(tmp_path, [sqs_message_m3("infra-a", "INFRA-A", infra=True), sqs_message_m3("good-b", "GOOD-B")], check=False)
        assert proc.returncode != 0
        assert response is None
        assert ledger == []

    def test_direct_and_simulator_invocation_agree(self, tmp_path):
        """Checks direct handler and simulator paths agree on failures and committed records."""
        records = [sqs_message_m3("parity-a", "PAR-A"), sqs_message_m3("parity-b", "PAR-B", poison=True)]
        _, direct_response, direct_ledger, _ = invoke_direct(tmp_path, records, ledger_name="direct.json")
        result, simulated_ledger, _ = run_sim_m3(tmp_path, write_batch_m3(tmp_path, records))
        assert [x["itemIdentifier"] for x in direct_response["batchItemFailures"]] == result["failed_message_ids"]
        assert {x["business_event_id"] for x in direct_ledger} == {x["business_event_id"] for x in simulated_ledger}


# ---- from test_m4.py ----
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def active_queue():
    return load_json(APP / "config" / "queues.json")["expected_active_queue_arn"]


def sqs_message(mid, event_id, *, amount=100, poison=False, malformed=False, extra=None):
    body = {"business_event_id": event_id, "account_id": "acct-durable", "amount_cents": amount, "currency": "USD", "operation": "ledger_credit"}
    if poison:
        body = {"business_event_id": event_id, "poison": True, "failure_reason": "schema_missing_amount"}
    if extra:
        body.update(extra)
    rendered = "{bad-json" if malformed else json.dumps(body, sort_keys=True)
    return {"messageId": mid, "receiptHandle": f"rh-{mid}", "eventSourceARN": active_queue(), "body": rendered, "attributes": {"ApproximateReceiveCount": "0"}, "messageAttributes": {}}


def write_batch(path, records):
    path.write_text(json.dumps({"queue_arn": active_queue(), "messages": records}, indent=2) + "\n")
    return path


def new_state(tmp_path, name="state"):
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    ledger, dlq, delivery = root / "ledger.json", root / "dlq.json", root / "delivery.json"
    ledger.write_text("[]\n")
    dlq.write_text("[]\n")
    delivery.write_text('{"receive_counts":{},"retired":{}}\n')
    return {"root": root, "ledger": ledger, "dlq": dlq, "delivery": delivery}


def run_sim_state(state, batch, *, cycles=1, extra_env=None, check=True, result_name=None):
    result = state["root"] / (result_name or f"result-{time.time_ns()}.json")
    env = os.environ.copy()
    env.update({
        "APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(state["ledger"]),
        "DLQ_STATE": str(state["dlq"]), "DELIVERY_STATE": str(state["delivery"]),
    })
    if extra_env:
        env.update(extra_env)
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", "batch", "--batch", str(batch), "--cycles", str(cycles), "--result", str(result)]
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    if check:
        assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = load_json(result) if result.exists() else None
    return proc, payload, load_json(state["ledger"]), load_json(state["dlq"])


def invoke(state, records, *, check=True):
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(state["ledger"])})
    proc = subprocess.run(["node", str(APP / "handler" / "invoke.mjs")], input=json.dumps({"Records": records}), text=True, capture_output=True, env=env, cwd=APP)
    if check:
        assert proc.returncode == 0, proc.stderr + proc.stdout
    response = json.loads(proc.stdout) if proc.returncode == 0 else None
    return proc, response, load_json(state["ledger"])


def popen_invoke(state, records):
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(state["ledger"])})
    return subprocess.Popen(["node", str(APP / "handler" / "invoke.mjs")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=APP), json.dumps({"Records": records})


class TestDurableReplay:
    def test_prior_mapping_iam_and_harness_files_are_preserved(self, tmp_path):
        """Ensures prior mapping, IAM, and trusted harness files remain intact."""
        assert hashlib.sha256((APP / "simulator" / "iam.go").read_bytes()).hexdigest() == "e2bb5dc987e3e1ef95ad21f9664559970587cd2a9466fdcac7ed262c1a8a74e2"
        assert hashlib.sha256((APP / "handler" / "invoke.mjs").read_bytes()).hexdigest() == "393e1f1d2a4a3859574e928c84c0d61ca14bf86465a0a9678302e1f5e9cee400"
        assert hashlib.sha256((APP / "scripts" / "run_simulation.py").read_bytes()).hexdigest() == "b6441b2798c31d4ce24d65594c332bf98547515698a7a39a5183c7c4ec5452b1"
        result_path = tmp_path / "mapping.json"
        proc = subprocess.run(
            [
                PYTHON,
                str(APP / "scripts" / "run_simulation.py"),
                "--scenario",
                "mapping",
                "--result",
                str(result_path),
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        mapping = load_json(result_path)
        queues = load_json(APP / "config" / "queues.json")
        assert mapping["event_source_arn"] == queues["expected_active_queue_arn"]
        assert mapping["function_response_types"] == ["ReportBatchItemFailures"]
        iam_path = tmp_path / "iam.json"
        proc = subprocess.run(
            [
                PYTHON,
                str(APP / "scripts" / "run_simulation.py"),
                "--scenario",
                "iam",
                "--result",
                str(iam_path),
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        iam = load_json(iam_path)
        required = {
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:ChangeMessageVisibility",
            "sqs:GetQueueAttributes",
        }
        assert iam["decisions"] == {action: "allowed" for action in required}
        assert iam["old_queue_receive"] != "allowed"

    def test_duplicate_business_event_deliveries_do_not_duplicate_rows(self, tmp_path):
        """Verifies duplicate business event deliveries do not duplicate rows."""
        state = new_state(tmp_path)
        _, result, ledger, _ = run_sim_state(state, APP / "data" / "duplicate_delivery_replay.json", cycles=2)
        assert result["access_denied"] is False
        assert [row["business_event_id"] for row in ledger].count("PAY-3001") == 1
        row = next(x for x in ledger if x["business_event_id"] == "PAY-3001")
        assert set(row["duplicate_message_ids"]) == {"msg-replay-3001-a", "msg-replay-3001-b"} - {row["message_id"]}

    def test_restart_replay_preserves_preexisting_committed_state(self, tmp_path):
        """Verifies restart replay preserves preexisting committed state."""
        state = new_state(tmp_path)
        state["ledger"].write_text(json.dumps([{"message_id": "old-primary", "business_event_id": "PAY-3001", "account_id": "acct-300", "amount_cents": 775, "currency": "USD", "operation": "ledger_credit", "status": "COMMITTED", "duplicate_message_ids": []}], indent=2) + "\n")
        run_sim_state(state, APP / "data" / "duplicate_delivery_replay.json", cycles=1)
        ledger = load_json(state["ledger"])
        assert len([x for x in ledger if x["business_event_id"] == "PAY-3001"]) == 1
        assert next(x for x in ledger if x["business_event_id"] == "PAY-3001")["message_id"] == "old-primary"

    def test_poison_moves_to_dlq_at_exact_max_receive_and_stops(self, tmp_path):
        """Verifies poison moves to dlq at exact max receive and stops."""
        state = new_state(tmp_path)
        batch = write_batch(state["root"] / "poison.json", [sqs_message("poison-a", "EV-POISON", poison=True)])
        _, result, ledger, dlq = run_sim_state(state, batch, cycles=5)
        assert ledger == []
        assert len(dlq) == 1 and dlq[0]["receive_count"] == 3
        assert result["receive_counts"]["poison-a"] == 3
        assert result["cycles"][3]["delivered"] == []
        assert result["cycles"][4]["delivered"] == []

    def test_dlq_entry_has_required_evidence_and_stable_reason(self, tmp_path):
        """Verifies dlq entry has required evidence and stable reason."""
        state = new_state(tmp_path)
        _, _, _, dlq = run_sim_state(state, APP / "data" / "duplicate_delivery_replay.json", cycles=5)
        entry = next(x for x in dlq if x["original_message_id"] == "msg-poison-3003")
        assert entry["business_event_id"] == "PAY-POISON-3003"
        assert entry["source_queue_arn"] == active_queue()
        assert entry["receive_count"] == 3
        assert entry["failure_reason"] == "schema_missing_amount"

    def test_malformed_message_redrives_with_stable_reason(self, tmp_path):
        """Verifies malformed message redrives with stable reason."""
        state = new_state(tmp_path)
        batch = write_batch(state["root"] / "bad.json", [sqs_message("malformed-z", "EV-Z", malformed=True)])
        _, _, _, dlq = run_sim_state(state, batch, cycles=4)
        assert len(dlq) == 1
        assert dlq[0]["original_message_id"] == "malformed-z"
        assert dlq[0]["failure_reason"] == "MALFORMED_JSON"

    def test_duplicate_evidence_is_unique_excludes_primary_and_is_ordered(self, tmp_path):
        """Verifies duplicate evidence is unique excludes primary and is ordered."""
        state = new_state(tmp_path)
        invoke(state, [sqs_message("primary", "EV-ORDER")])
        invoke(state, [sqs_message("alt-b", "EV-ORDER")])
        invoke(state, [sqs_message("alt-a", "EV-ORDER"), sqs_message("alt-b", "EV-ORDER")])
        row = load_json(state["ledger"])[0]
        assert row["message_id"] == "primary"
        assert row["duplicate_message_ids"] == ["alt-b", "alt-a"]

    def test_handler_itself_is_idempotent_without_simulator_deduplication(self, tmp_path):
        """Verifies handler itself is idempotent without simulator deduplication."""
        state = new_state(tmp_path)
        _, response, ledger = invoke(state, [sqs_message("direct-a", "EV-DIRECT"), sqs_message("direct-b", "EV-DIRECT")])
        assert response == {"batchItemFailures": []}
        assert len(ledger) == 1
        assert set([ledger[0]["message_id"], *ledger[0]["duplicate_message_ids"]]) == {"direct-a", "direct-b"}

    def test_preexisting_dlq_record_prevents_redelivery_and_duplicate_append(self, tmp_path):
        """Verifies preexisting dlq record prevents redelivery and duplicate append."""
        state = new_state(tmp_path)
        state["dlq"].write_text(json.dumps([{"message_id": "dlq-poison-a", "original_message_id": "poison-a", "business_event_id": "EV-POISON", "source_queue_arn": active_queue(), "failure_reason": "schema_missing_amount", "receive_count": 3}], indent=2) + "\n")
        batch = write_batch(state["root"] / "poison.json", [sqs_message("poison-a", "EV-POISON", poison=True)])
        _, result, _, dlq = run_sim_state(state, batch, cycles=2)
        assert result["delivered_message_ids"] == []
        assert len(dlq) == 1

    def test_concurrent_duplicate_processes_commit_one_business_row(self, tmp_path):
        """Verifies concurrent duplicate processes commit one business row."""
        state = new_state(tmp_path)
        p1, i1 = popen_invoke(state, [sqs_message("con-a", "EV-CONCURRENT", extra={"fixture_delay_ms": 750})])
        p2, i2 = popen_invoke(state, [sqs_message("con-b", "EV-CONCURRENT", extra={"fixture_delay_ms": 750})])
        out1, err1 = p1.communicate(i1, timeout=15)
        out2, err2 = p2.communicate(i2, timeout=15)
        assert p1.returncode == 0, err1
        assert p2.returncode == 0, err2
        assert json.loads(out1) == {"batchItemFailures": []}
        assert json.loads(out2) == {"batchItemFailures": []}
        ledger = load_json(state["ledger"])
        assert len(ledger) == 1
        assert set([ledger[0]["message_id"], *ledger[0]["duplicate_message_ids"]]) == {"con-a", "con-b"}

    def test_concurrent_distinct_processes_do_not_lose_rows(self, tmp_path):
        """Verifies concurrent distinct processes do not lose rows."""
        state = new_state(tmp_path)
        p1, i1 = popen_invoke(state, [sqs_message("distinct-a", "EV-A", extra={"fixture_delay_ms": 750})])
        p2, i2 = popen_invoke(state, [sqs_message("distinct-b", "EV-B", extra={"fixture_delay_ms": 750})])
        _, e1 = p1.communicate(i1, timeout=15)
        _, e2 = p2.communicate(i2, timeout=15)
        assert p1.returncode == 0, e1
        assert p2.returncode == 0, e2
        assert {x["business_event_id"] for x in load_json(state["ledger"])} == {"EV-A", "EV-B"}

    def test_crash_after_journal_commit_recovers_without_duplicate_row(self, tmp_path):
        """Verifies crash after journal commit recovers without duplicate row."""
        state = new_state(tmp_path)
        crash = sqs_message("crash-a", "EV-CRASH-J", extra={"fixture_crash_after_journal_commit": True})
        proc, _, _ = invoke(state, [crash], check=False)
        assert proc.returncode == 86
        _, response, ledger = invoke(state, [sqs_message("retry-b", "EV-CRASH-J")])
        assert response == {"batchItemFailures": []}
        assert len(ledger) == 1
        assert set([ledger[0]["message_id"], *ledger[0]["duplicate_message_ids"]]) == {"crash-a", "retry-b"}

    def test_crash_during_atomic_replace_recovers_from_journal(self, tmp_path):
        """Verifies crash during atomic replace recovers from journal."""
        state = new_state(tmp_path)
        proc, _, _ = invoke(state, [sqs_message("replace-a", "EV-REPLACE", extra={"fixture_crash_during_ledger_replace": True})], check=False)
        assert proc.returncode == 87
        invoke(state, [sqs_message("replace-b", "EV-REPLACE")])
        ledger = load_json(state["ledger"])
        assert len(ledger) == 1
        assert set([ledger[0]["message_id"], *ledger[0]["duplicate_message_ids"]]) == {"replace-a", "replace-b"}

    def test_crash_after_ledger_commit_before_ack_is_idempotent(self, tmp_path):
        """Verifies crash after ledger commit before ack is idempotent."""
        state = new_state(tmp_path)
        proc, _, _ = invoke(state, [sqs_message("ack-a", "EV-ACK", extra={"fixture_crash_after_commit": True})], check=False)
        assert proc.returncode == 88
        invoke(state, [sqs_message("ack-b", "EV-ACK")])
        ledger = load_json(state["ledger"])
        assert len(ledger) == 1
        assert set([ledger[0]["message_id"], *ledger[0]["duplicate_message_ids"]]) == {"ack-a", "ack-b"}

    def test_truncated_uncommitted_journal_tail_is_ignored(self, tmp_path):
        """Verifies truncated uncommitted journal tail is ignored."""
        state = new_state(tmp_path)
        invoke(state, [sqs_message("tail-a", "EV-TAIL-A")])
        journal = Path(str(state["ledger"]) + ".journal")
        with journal.open("ab") as fh:
            fh.write(b'{"seq":999,"snapshot":')
        invoke(state, [sqs_message("tail-b", "EV-TAIL-B")])
        assert {x["business_event_id"] for x in load_json(state["ledger"])} == {"EV-TAIL-A", "EV-TAIL-B"}

    def test_committed_journal_corruption_fails_closed(self, tmp_path):
        """Verifies committed journal corruption fails closed."""
        state = new_state(tmp_path)
        invoke(state, [sqs_message("corrupt-a", "EV-CORRUPT-A")])
        journal = Path(str(state["ledger"]) + ".journal")
        record = json.loads(journal.read_text().splitlines()[0])
        record["checksum"] = "0" * 64
        journal.write_text(json.dumps(record) + "\n")
        proc, _, ledger = invoke(state, [sqs_message("corrupt-b", "EV-CORRUPT-B")], check=False)
        assert proc.returncode != 0
        assert [x["business_event_id"] for x in ledger] == ["EV-CORRUPT-A"]

    def test_journal_checksum_matches_canonical_sha256_payload(self, tmp_path):
        """Independently verifies journal checksum over sequence and snapshot."""
        state = new_state(tmp_path)
        invoke(state, [sqs_message("checksum-a", "EV-CHECKSUM")])
        journal = Path(str(state["ledger"]) + ".journal")
        record = json.loads(journal.read_text().splitlines()[0])
        payload = json.dumps(
            {"seq": record["seq"], "snapshot": record["snapshot"]},
            separators=(",", ":"),
        )
        assert record["checksum"] == hashlib.sha256(payload.encode()).hexdigest()

    def test_stale_dead_process_lock_is_reclaimed(self, tmp_path):
        """Verifies stale dead process lock is reclaimed."""
        state = new_state(tmp_path)
        lock = Path(str(state["ledger"]) + ".lock")
        lock.write_text(json.dumps({"pid": 99999999, "created_ms": 0}) + "\n")
        _, response, ledger = invoke(state, [sqs_message("lock-a", "EV-LOCK")])
        assert response == {"batchItemFailures": []}
        assert [x["business_event_id"] for x in ledger] == ["EV-LOCK"]
        assert not lock.exists()

    def test_receive_counts_persist_across_separate_simulator_processes(self, tmp_path):
        """Verifies receive counts persist across separate simulator processes."""
        state = new_state(tmp_path)
        batch = write_batch(state["root"] / "poison.json", [sqs_message("persist-poison", "EV-PERSIST", poison=True)])
        _, r1, _, _ = run_sim_state(state, batch, cycles=1)
        _, r2, _, _ = run_sim_state(state, batch, cycles=1)
        _, r3, _, dlq = run_sim_state(state, batch, cycles=1)
        assert r1["receive_counts"]["persist-poison"] == 1
        assert r2["receive_counts"]["persist-poison"] == 2
        assert r3["receive_counts"]["persist-poison"] == 3
        assert len(dlq) == 1 and dlq[0]["receive_count"] == 3

    def test_dlq_append_crash_converges_exactly_once(self, tmp_path):
        """Verifies dlq append crash converges exactly once."""
        state = new_state(tmp_path)
        batch = write_batch(state["root"] / "poison.json", [sqs_message("dlq-crash", "EV-DLQ", poison=True)])
        run_sim_state(state, batch, cycles=1)
        run_sim_state(state, batch, cycles=1)
        proc, _, _, dlq = run_sim_state(state, batch, cycles=1, extra_env={"SIMULATOR_CRASH_POINT": "after_dlq_append"}, check=False)
        assert proc.returncode != 0 and len(dlq) == 1
        _, result, _, dlq = run_sim_state(state, batch, cycles=2)
        assert result["delivered_message_ids"] == []
        assert len(dlq) == 1


# ---- from test_m5.py ----
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def contract(root=APP):
    return load_json(root / "config" / "cutover_contract.json")


def active_queue(root=APP):
    return contract(root)["active_source_queue_arn"]


def message(mid, event_id, *, version=None, epoch=None, queue=None, amount=100, account="acct-dyn", currency="USD", operation="ledger_credit", nested=False, poison=False, malformed=False):
    body = {"business_event_id": event_id, "account_id": account, "amount_cents": amount, "currency": currency, "operation": operation}
    if poison:
        body = {"business_event_id": event_id, "poison": True, "failure_reason": "schema_missing_amount"}
    if version is not None:
        if nested and version == 2 and not poison:
            body = {"event_version": 2, "cutover_epoch": epoch or contract()["cutover_epoch"], "detail": body}
        else:
            body["event_version"] = version
            if version == 2:
                body["cutover_epoch"] = epoch or contract()["cutover_epoch"]
    rendered = "{bad-json" if malformed else json.dumps(body, sort_keys=True)
    return {"messageId": mid, "receiptHandle": f"rh-{mid}", "eventSourceARN": queue or active_queue(), "body": rendered, "attributes": {"ApproximateReceiveCount": "0"}, "messageAttributes": {}}


def new_state_v5(tmp_path, name="state"):
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    ledger, dlq, delivery = root / "ledger.json", root / "dlq.json", root / "delivery.json"
    ledger.write_text("[]\n")
    dlq.write_text("[]\n")
    delivery.write_text('{"receive_counts":{},"retired":{}}\n')
    return {"root": root, "ledger": ledger, "dlq": dlq, "delivery": delivery}


def invoke_v5(state, records, *, root=APP, check=True):
    env = os.environ.copy()
    env.update({"APP_ROOT": str(root), "SIDE_EFFECT_LEDGER": str(state["ledger"])})
    proc = subprocess.run(["node", str(root / "handler" / "invoke.mjs")], input=json.dumps({"Records": records}), text=True, capture_output=True, env=env, cwd=root)
    if check:
        assert proc.returncode == 0, proc.stderr + proc.stdout
    return proc, json.loads(proc.stdout) if proc.returncode == 0 else None, load_json(state["ledger"])


def run_sim_v5(state, batch, cycles=1):
    result = state["root"] / f"result-{time.time_ns()}.json"
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(state["ledger"]), "DLQ_STATE": str(state["dlq"]), "DELIVERY_STATE": str(state["delivery"])})
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", "batch", "--batch", str(batch), "--cycles", str(cycles), "--result", str(result)]
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(state["ledger"]), load_json(state["dlq"])


def write_batch_v5(state, records, name="batch.json"):
    path = state["root"] / name
    path.write_text(json.dumps({"queue_arn": active_queue(), "messages": records}, indent=2) + "\n")
    return path


def popen_invoke_v5(state, records):
    env = os.environ.copy()
    env.update({"APP_ROOT": str(APP), "SIDE_EFFECT_LEDGER": str(state["ledger"])})
    proc = subprocess.Popen(["node", str(APP / "handler" / "invoke.mjs")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=APP)
    return proc, json.dumps({"Records": records})


class TestDurabilityRegression:
    def test_prior_mapping_iam_and_harness_files_are_preserved(self, tmp_path):
        """Ensures prior mapping, IAM, and trusted harness files remain intact."""
        assert hashlib.sha256((APP / "simulator" / "iam.go").read_bytes()).hexdigest() == "e2bb5dc987e3e1ef95ad21f9664559970587cd2a9466fdcac7ed262c1a8a74e2"
        assert hashlib.sha256((APP / "handler" / "invoke.mjs").read_bytes()).hexdigest() == "393e1f1d2a4a3859574e928c84c0d61ca14bf86465a0a9678302e1f5e9cee400"
        assert hashlib.sha256((APP / "scripts" / "run_simulation.py").read_bytes()).hexdigest() == "b6441b2798c31d4ce24d65594c332bf98547515698a7a39a5183c7c4ec5452b1"
        result_path = tmp_path / "mapping.json"
        proc = subprocess.run(
            [
                PYTHON,
                str(APP / "scripts" / "run_simulation.py"),
                "--scenario",
                "mapping",
                "--result",
                str(result_path),
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        mapping = load_json(result_path)
        queues = load_json(APP / "config" / "queues.json")
        assert mapping["event_source_arn"] == queues["expected_active_queue_arn"]
        assert mapping["function_response_types"] == ["ReportBatchItemFailures"]
        iam_path = tmp_path / "iam.json"
        proc = subprocess.run(
            [
                PYTHON,
                str(APP / "scripts" / "run_simulation.py"),
                "--scenario",
                "iam",
                "--result",
                str(iam_path),
            ],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        iam = load_json(iam_path)
        required = {
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:ChangeMessageVisibility",
            "sqs:GetQueueAttributes",
        }
        assert iam["decisions"] == {action: "allowed" for action in required}
        assert iam["old_queue_receive"] != "allowed"

    def test_duplicate_business_event_deliveries_do_not_duplicate_rows(self, tmp_path):
        """Verifies duplicate business events commit one ledger row with duplicate evidence."""
        state = new_state_v5(tmp_path)
        _, response, ledger = invoke_v5(state, [message("dup-a", "EV-DUP"), message("dup-b", "EV-DUP")])
        assert response == {"batchItemFailures": []}
        assert len(ledger) == 1
        assert set([ledger[0]["message_id"], *ledger[0]["duplicate_message_ids"]]) == {"dup-a", "dup-b"}

    def test_restart_replay_preserves_historical_row_without_digest(self, tmp_path):
        """Ensures replay preserves historical rows that predate digest metadata."""
        state = new_state_v5(tmp_path)
        state["ledger"].write_text(json.dumps([{"message_id": "historic-a", "business_event_id": "EV-HIST", "account_id": "acct-dyn", "amount_cents": 100, "currency": "USD", "operation": "ledger_credit", "status": "COMMITTED", "duplicate_message_ids": []}], indent=2) + "\n")
        _, response, ledger = invoke_v5(state, [message("historic-b", "EV-HIST", version=2)])
        assert response == {"batchItemFailures": []}
        assert len(ledger) == 1 and ledger[0]["duplicate_message_ids"] == ["historic-b"]

    def test_poison_and_malformed_messages_redrive_with_stable_reasons(self, tmp_path):
        """Checks poison and malformed messages redrive to DLQ with stable reasons."""
        state = new_state_v5(tmp_path)
        batch = write_batch_v5(state, [message("poison-a", "EV-P", poison=True), message("malformed-a", "EV-M", malformed=True)])
        _, _, dlq = run_sim_v5(state, batch, cycles=7)
        reasons = {x["original_message_id"]: x["failure_reason"] for x in dlq}
        assert reasons == {"poison-a": "schema_missing_amount", "malformed-a": "MALFORMED_JSON"}
        assert all(x["receive_count"] == 3 and x["source_queue_arn"] == active_queue() for x in dlq)

    def test_duplicate_evidence_remains_unique_and_excludes_primary(self, tmp_path):
        """Ensures duplicate evidence is unique and excludes the primary message id."""
        state = new_state_v5(tmp_path)
        invoke_v5(state, [message("p", "EV-EVID")])
        invoke_v5(state, [message("a", "EV-EVID"), message("a", "EV-EVID"), message("b", "EV-EVID")])
        row = load_json(state["ledger"])[0]
        assert row["message_id"] == "p"
        assert row["duplicate_message_ids"] == ["a", "b"]

    def test_ledger_remains_flat_json_array(self, tmp_path):
        """Verifies the ledger remains a flat JSON array after writes."""
        state = new_state_v5(tmp_path)
        invoke_v5(state, [message("flat-a", "EV-FLAT")])
        assert isinstance(load_json(state["ledger"]), list)


class TestCutover:
    def test_cutover_contract_is_explicit_and_fail_closed(self):
        """Checks the cutover contract declares fail-closed runtime requirements."""
        c = contract()
        q = load_json(APP / "config" / "queues.json")
        assert c["active_source_queue_arn"] == q["expected_active_queue_arn"]
        assert c["legacy_source_queue_arn"] == q["old_queue_arn"]
        assert c["accepted_event_versions"] == [1, 2]
        assert c["required_operation"] == "ledger_credit"
        assert c["conflict_policy"] == "FAIL_CLOSED"
        assert c["missing_event_version_defaults_to"] == 1
        assert c["ledger_format"] == "flat_array"

    def test_version_one_and_missing_version_remain_compatible(self, tmp_path):
        """Ensures version one and missing-version events remain backward compatible."""
        state = new_state_v5(tmp_path)
        _, response, ledger = invoke_v5(state, [message("v1-a", "EV-V1", version=1), message("implicit-a", "EV-IMPLICIT")])
        assert response == {"batchItemFailures": []}
        assert {x["business_event_id"] for x in ledger} == {"EV-V1", "EV-IMPLICIT"}

    def test_version_two_requires_exact_cutover_epoch_without_blocking_peer(self, tmp_path):
        """Verifies version two events require the exact cutover epoch without blocking valid peers."""
        state = new_state_v5(tmp_path)
        records = [message("stale-a", "EV-STALE", version=2, epoch="2026-06-24T09:00:00Z"), message("fresh-b", "EV-FRESH", version=2)]
        _, response, ledger = invoke_v5(state, records)
        assert response["batchItemFailures"] == [{"itemIdentifier": "stale-a", "failureClassification": "STALE_CUTOVER_EPOCH"}]
        assert [x["business_event_id"] for x in ledger] == ["EV-FRESH"]

    def test_legacy_and_unknown_sources_are_fenced(self, tmp_path):
        """Confirms legacy and unknown source queues are fenced before ledger side effects."""
        state = new_state_v5(tmp_path)
        records = [
            message("old-a", "EV-OLD", version=2, queue=contract()["legacy_source_queue_arn"]),
            message("rogue-a", "EV-ROGUE", version=2, queue="arn:aws:sqs:us-east-1:999999999999:rogue"),
        ]
        _, response, ledger = invoke_v5(state, records)
        assert response["batchItemFailures"] == [
            {"itemIdentifier": "old-a", "failureClassification": "STALE_SOURCE_QUEUE"},
            {"itemIdentifier": "rogue-a", "failureClassification": "STALE_SOURCE_QUEUE"},
        ]
        assert ledger == []

    def test_unsupported_version_isolated_without_side_effect(self, tmp_path):
        """Ensures unsupported versions fail individually without ledger side effects."""
        state = new_state_v5(tmp_path)
        _, response, ledger = invoke_v5(state, [message("bad-v", "EV-BADV", version=3), message("good-v", "EV-GOODV", version=2)])
        assert response["batchItemFailures"] == [{"itemIdentifier": "bad-v", "failureClassification": "UNSUPPORTED_EVENT_VERSION"}]
        assert [x["business_event_id"] for x in ledger] == ["EV-GOODV"]

    @pytest.mark.parametrize(("field", "replacement"), [("account_id", "other"), ("amount_cents", 999), ("currency", "EUR"), ("operation", "ledger_debit")])
    def test_all_immutable_changes_are_idempotency_conflicts(self, tmp_path, field, replacement):
        """Checks immutable field changes on duplicate business events fail as idempotency conflicts."""
        state = new_state_v5(tmp_path)
        first = message("base-a", f"EV-{field}", version=2)
        second = message("changed-b", f"EV-{field}", version=2)
        body = json.loads(second["body"])
        body[field] = replacement
        second["body"] = json.dumps(body, sort_keys=True)
        _, response, ledger = invoke_v5(state, [first, second])
        assert response["batchItemFailures"] == [{"itemIdentifier": "changed-b", "failureClassification": "IDEMPOTENCY_CONFLICT"}]
        assert len(ledger) == 1 and ledger[0]["duplicate_message_ids"] == []

    def test_identical_v1_then_nested_v2_replay_records_evidence(self, tmp_path):
        """Verifies compatible v1 and nested v2 replays record duplicate evidence."""
        state = new_state_v5(tmp_path)
        _, response, ledger = invoke_v5(state, [message("v1-primary", "EV-CROSS", version=1), message("v2-alt", "EV-CROSS", version=2, nested=True)])
        assert response == {"batchItemFailures": []}
        assert len(ledger) == 1 and ledger[0]["duplicate_message_ids"] == ["v2-alt"]

    def test_new_unsupported_operation_is_classified_without_side_effect(self, tmp_path):
        """Ensures unsupported operations are classified without ledger side effects."""
        state = new_state_v5(tmp_path)
        _, response, ledger = invoke_v5(state, [message("op-bad", "EV-BADOP", version=2, operation="ledger_debit")])
        assert response["batchItemFailures"] == [{"itemIdentifier": "op-bad", "failureClassification": "UNSUPPORTED_OPERATION"}]
        assert ledger == []

    def test_existing_operation_change_is_conflict_not_unsupported_operation(self, tmp_path):
        """Confirms operation changes on existing events are idempotency conflicts."""
        state = new_state_v5(tmp_path)
        _, response, ledger = invoke_v5(state, [message("op-a", "EV-OP", version=2), message("op-b", "EV-OP", version=2, operation="ledger_debit")])
        assert response["batchItemFailures"] == [{"itemIdentifier": "op-b", "failureClassification": "IDEMPOTENCY_CONFLICT"}]
        assert len(ledger) == 1 and ledger[0]["operation"] == "ledger_credit"

    def test_combined_invalid_records_follow_documented_precedence(self, tmp_path):
        """Checks invalid records follow the documented classification precedence."""
        state = new_state_v5(tmp_path)
        wrong = message("wrong-source", "EV-X", version=3, queue=contract()["legacy_source_queue_arn"])
        bad_version = message("bad-version", "EV-Y", version=3, epoch="bad")
        stale_epoch = message("stale-epoch", "EV-Z", version=2, epoch="bad", operation="ledger_debit")
        _, response, ledger = invoke_v5(state, [wrong, bad_version, stale_epoch])
        assert response["batchItemFailures"] == [
            {"itemIdentifier": "wrong-source", "failureClassification": "STALE_SOURCE_QUEUE"},
            {"itemIdentifier": "bad-version", "failureClassification": "UNSUPPORTED_EVENT_VERSION"},
            {"itemIdentifier": "stale-epoch", "failureClassification": "STALE_CUTOVER_EPOCH"},
        ]
        assert ledger == []

    def test_stale_source_duplicate_cannot_append_evidence(self, tmp_path):
        """Ensures stale-source duplicates cannot append duplicate evidence."""
        state = new_state_v5(tmp_path)
        invoke_v5(state, [message("primary", "EV-FENCE", version=2)])
        _, response, ledger = invoke_v5(state, [message("stale-alt", "EV-FENCE", version=2, queue=contract()["legacy_source_queue_arn"])])
        assert response["batchItemFailures"][0]["failureClassification"] == "STALE_SOURCE_QUEUE"
        assert ledger[0]["duplicate_message_ids"] == []

    def test_unsupported_version_duplicate_cannot_append_evidence(self, tmp_path):
        """Ensures unsupported-version duplicates cannot append duplicate evidence."""
        state = new_state_v5(tmp_path)
        invoke_v5(state, [message("primary", "EV-VFENCE", version=2)])
        _, response, ledger = invoke_v5(state, [message("bad-alt", "EV-VFENCE", version=9)])
        assert response["batchItemFailures"][0]["failureClassification"] == "UNSUPPORTED_EVENT_VERSION"
        assert ledger[0]["duplicate_message_ids"] == []

    def test_stale_epoch_precedes_existing_payload_conflict(self, tmp_path):
        """Verifies stale epoch classification takes precedence over payload conflict."""
        state = new_state_v5(tmp_path)
        invoke_v5(state, [message("primary", "EV-EPOCH-PRE", version=2, amount=100)])
        _, response, ledger = invoke_v5(state, [message("bad", "EV-EPOCH-PRE", version=2, epoch="old", amount=999)])
        assert response["batchItemFailures"] == [{"itemIdentifier": "bad", "failureClassification": "STALE_CUTOVER_EPOCH"}]
        assert ledger[0]["amount_cents"] == 100 and ledger[0]["duplicate_message_ids"] == []

    def test_contract_values_are_data_driven_in_isolated_workspace(self, tmp_path):
        """Checks copied contract values drive source, epoch, classification, and operation admission."""
        root = tmp_path / "cloned-app"
        shutil.copytree(APP / "handler", root / "handler")
        shutil.copytree(APP / "config", root / "config")
        cpath = root / "config" / "cutover_contract.json"
        c = load_json(cpath)
        c["active_source_queue_arn"] = "arn:aws:sqs:eu-central-1:123456789012:blue"
        c["cutover_epoch"] = "2030-01-02T03:04:05Z"
        c["required_operation"] = "ledger_debit"
        c["failure_classifications"]["stale_source"] = "CUSTOM_SOURCE_FENCE"
        c["failure_classifications"]["unsupported_version"] = "CUSTOM_VERSION_FENCE"
        c["failure_classifications"]["stale_epoch"] = "CUSTOM_EPOCH_FENCE"
        c["failure_classifications"]["unsupported_operation"] = "CUSTOM_OPERATION_FENCE"
        c["failure_classifications"]["idempotency_conflict"] = "CUSTOM_CONFLICT_FENCE"
        cpath.write_text(json.dumps(c, indent=2) + "\n")
        state = new_state_v5(tmp_path, "clone-state")
        good = message("clone-good", "EV-CLONE", version=2, operation="ledger_debit")
        good["eventSourceARN"] = c["active_source_queue_arn"]
        body = json.loads(good["body"])
        body["cutover_epoch"] = c["cutover_epoch"]
        good["body"] = json.dumps(body)
        stale = json.loads(json.dumps(good))
        stale["messageId"] = "clone-stale"
        stale["eventSourceARN"] = active_queue()
        bad_version = json.loads(json.dumps(good))
        bad_version["messageId"] = "clone-version"
        bad_version_body = json.loads(bad_version["body"])
        bad_version_body["business_event_id"] = "EV-BAD-VERSION"
        bad_version_body["event_version"] = 9
        bad_version["body"] = json.dumps(bad_version_body, sort_keys=True)
        stale_epoch = json.loads(json.dumps(good))
        stale_epoch["messageId"] = "clone-epoch"
        stale_epoch_body = json.loads(stale_epoch["body"])
        stale_epoch_body["business_event_id"] = "EV-BAD-EPOCH"
        stale_epoch_body["cutover_epoch"] = "2029-01-02T03:04:05Z"
        stale_epoch["body"] = json.dumps(stale_epoch_body, sort_keys=True)
        wrong_operation = json.loads(json.dumps(good))
        wrong_operation["messageId"] = "clone-credit"
        wrong_operation_body = json.loads(wrong_operation["body"])
        wrong_operation_body["business_event_id"] = "EV-CREDIT"
        wrong_operation_body["operation"] = "ledger_credit"
        wrong_operation["body"] = json.dumps(wrong_operation_body, sort_keys=True)
        _, response, ledger = invoke_v5(state, [good], root=root)
        assert response == {"batchItemFailures": []}
        conflict = json.loads(json.dumps(good))
        conflict["messageId"] = "clone-conflict"
        conflict_body = json.loads(conflict["body"])
        conflict_body["amount_cents"] = 999
        conflict["body"] = json.dumps(conflict_body, sort_keys=True)
        _, response, ledger = invoke_v5(
            state,
            [stale, bad_version, stale_epoch, wrong_operation, conflict],
            root=root,
        )
        assert response["batchItemFailures"] == [
            {
                "itemIdentifier": "clone-stale",
                "failureClassification": "CUSTOM_SOURCE_FENCE",
            },
            {
                "itemIdentifier": "clone-version",
                "failureClassification": "CUSTOM_VERSION_FENCE",
            },
            {
                "itemIdentifier": "clone-epoch",
                "failureClassification": "CUSTOM_EPOCH_FENCE",
            },
            {
                "itemIdentifier": "clone-credit",
                "failureClassification": "CUSTOM_OPERATION_FENCE",
            },
            {
                "itemIdentifier": "clone-conflict",
                "failureClassification": "CUSTOM_CONFLICT_FENCE",
            },
        ]
        assert [x["business_event_id"] for x in ledger] == ["EV-CLONE"]

    def test_cutover_contract_is_enforced_through_simulator_path(self, tmp_path):
        """Verifies cutover source and epoch rules are enforced through the simulator path."""
        state = new_state_v5(tmp_path)
        stale = message("sim-stale", "EV-SIM-STALE", version=2, epoch="2026-06-24T09:00:00Z")
        fresh = message("sim-fresh", "EV-SIM-FRESH", version=2)
        old_source = message(
            "sim-old-source",
            "EV-SIM-OLD",
            version=2,
            queue=contract()["legacy_source_queue_arn"],
        )
        batch = write_batch_v5(state, [stale, fresh, old_source])
        result, ledger, dlq = run_sim_v5(state, batch)
        assert result["failed_message_ids"] == ["sim-stale", "sim-old-source"]
        assert result["deleted_message_ids"] == ["sim-fresh"]
        assert [row["business_event_id"] for row in ledger] == ["EV-SIM-FRESH"]
        assert dlq == []

    def test_concurrent_conflicting_first_deliveries_commit_one_and_reject_one(self, tmp_path):
        """Ensures concurrent first deliveries commit one row and reject the conflicting peer."""
        state = new_state_v5(tmp_path)
        p1, i1 = popen_invoke_v5(state, [message("race-a", "EV-RACE", version=2, amount=100)])
        p2, i2 = popen_invoke_v5(state, [message("race-b", "EV-RACE", version=2, amount=999)])
        out1, err1 = p1.communicate(i1, timeout=10)
        out2, err2 = p2.communicate(i2, timeout=10)
        assert p1.returncode == 0, err1
        assert p2.returncode == 0, err2
        responses = [json.loads(out1), json.loads(out2)]
        failures = [f for r in responses for f in r["batchItemFailures"]]
        assert len(failures) == 1 and failures[0]["failureClassification"] == "IDEMPOTENCY_CONFLICT"
        ledger = load_json(state["ledger"])
        assert len(ledger) == 1 and ledger[0]["amount_cents"] in {100, 999}


class TestDataValidation:
    def _load_dataset_messages(self, name):
        dataset = load_json(APP / "data" / name)
        assert isinstance(dataset, dict)
        assert isinstance(dataset.get("messages"), list)
        assert dataset["messages"], "dataset must contain at least one message"
        return dataset["messages"]

    def _normalize_for_active_contract(self, records):
        cfg = contract()
        out = json.loads(json.dumps(records))
        for rec in out:
            rec["eventSourceARN"] = cfg["active_source_queue_arn"]
            body = json.loads(rec["body"])
            if body.get("event_version") == 2:
                body["cutover_epoch"] = cfg["cutover_epoch"]
            rec["body"] = json.dumps(body, sort_keys=True)
        return out

    def test_new_data_fixtures_have_valid_record_shape(self):
        """Ensures added data fixtures are structurally valid and message IDs are unique."""
        for name in ("data_quality_matrix_batch.json", "data_duplicate_evidence_batch.json"):
            dataset = load_json(APP / "data" / name)
            assert isinstance(dataset.get("queue_arn"), str) and dataset["queue_arn"].startswith("arn:aws:sqs:")
            messages = dataset["messages"]
            assert all(isinstance(m.get("messageId"), str) and m["messageId"] for m in messages)
            assert len(messages) == len({m["messageId"] for m in messages})
            assert all("receiptHandle" in m and "eventSourceARN" in m and "body" in m for m in messages)
            assert all(isinstance(m.get("attributes"), dict) and isinstance(m.get("messageAttributes"), dict) for m in messages)

    def test_data_quality_matrix_drives_contract_classification_and_partial_success(self, tmp_path):
        """Validates fixture-driven mixed-quality records execute with stable response shape and durable writes."""
        state = new_state_v5(tmp_path, "data-matrix")
        records = self._normalize_for_active_contract(self._load_dataset_messages("data_quality_matrix_batch.json"))
        _, response, ledger = invoke_v5(state, records)
        assert list(response) == ["batchItemFailures"]
        assert isinstance(response["batchItemFailures"], list)
        assert {row["business_event_id"] for row in ledger} == {"EV-DATA-7001", "EV-DATA-7002", "EV-DATA-7003"}

    def test_duplicate_evidence_dataset_preserves_primary_and_unique_alternates(self, tmp_path):
        """Verifies fixture-driven duplicate deliveries ingest deterministically with stable IDs."""
        state = new_state_v5(tmp_path, "data-dup")
        records = self._normalize_for_active_contract(self._load_dataset_messages("data_duplicate_evidence_batch.json"))
        primary, alternate, unique = records[0], records[1], records[2]
        _, response, _ = invoke_v5(state, [primary, unique])
        assert response == {"batchItemFailures": []}
        _, response, ledger = invoke_v5(state, [alternate])
        assert response == {"batchItemFailures": []}
        assert len(ledger) == 3
        assert [row["message_id"] for row in ledger] == [
            "data-dup-primary-7101",
            "data-unique-7103",
            "data-dup-alt-7102",
        ]
        assert {row["business_event_id"] for row in ledger} == {"EV-DATA-DUP-710", "EV-DATA-UNIQ-711"}
