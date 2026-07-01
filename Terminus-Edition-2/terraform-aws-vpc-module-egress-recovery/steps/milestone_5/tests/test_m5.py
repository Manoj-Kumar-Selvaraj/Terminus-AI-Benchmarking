import json

from vpc_test_support import (
    cfg,
    data_rts,
    default_target,
    journal_lines,
    make_root,
    run,
    save_cfg,
    state,
)


class TestMilestone5:
    def test_torn_final_journal_record_is_repaired_on_resume(self):
        """a torn final JSONL journal record is truncated and recovery resumes."""
        td, root = make_root()
        try:
            journal_path = root / "state/recovery_journal.jsonl"
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            _, plan = run(root, "plan", check=True)
            digest = plan["config_digest"]
            journal_path.write_text(
                json.dumps(
                    {
                        "event": "route_plan_written",
                        "owner": "owner-a",
                        "config_digest": digest,
                    }
                )
                + '\n{"event":"apply_committed"'
            )
            run(root, "resume", owner="owner-a", check=True)
            assert state(root)["schema_version"] == "vpc-recovery.aws.1"
            lines = journal_lines(root)
            assert lines[0]["event"] == "route_plan_written"
            assert all("event" in entry for entry in lines)
            assert "apply_committed" not in journal_path.read_text().split("\n")[1]
        finally:
            td.cleanup()

    def test_middle_journal_corruption_fails_closed(self):
        """corruption before the final line is not silently repaired."""
        td, root = make_root()
        try:
            journal_path = root / "state/recovery_journal.jsonl"
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            journal_path.write_text(
                json.dumps(
                    {
                        "event": "route_plan_written",
                        "owner": "owner-a",
                        "config_digest": "x",
                    }
                )
                + "\nnot-json\n"
                + json.dumps(
                    {
                        "event": "apply_committed",
                        "owner": "owner-a",
                        "config_digest": "x",
                    }
                )
                + "\n"
            )
            result, out = run(root, "resume", owner="owner-a")
            assert result.returncode != 0 and "journal corruption" in out["error"]
        finally:
            td.cleanup()

    def test_lost_response_after_endpoint_commit_can_resume(self):
        """a crash after endpoint commit can be resumed without duplicating associations."""
        td, root = make_root()
        try:
            _, plan = run(root, "plan", check=True)
            result, _ = run(root, "apply", owner="owner-a", fail_after="endpoint_commit")
            assert result.returncode != 0
            run(root, "resume", owner="owner-a", check=True)
            recovered = state(root)
            for ep in recovered["gateway_endpoints"]:
                assert len(ep["route_table_ids"]) == len(set(ep["route_table_ids"]))
            for rec in journal_lines(root):
                assert rec.get("config_digest") == plan["config_digest"], rec
        finally:
            td.cleanup()

    def test_different_owner_cannot_resume_active_journal(self):
        """an active owner fences other owners from resuming its interrupted operation."""
        td, root = make_root()
        try:
            result, _ = run(root, "apply", owner="owner-a", fail_after="endpoint_commit")
            assert result.returncode != 0
            result2, out2 = run(root, "resume", owner="owner-b")
            assert result2.returncode != 0 and "stale owner" in out2["error"]
        finally:
            td.cleanup()

    def test_changed_config_digest_cannot_resume_same_operation(self):
        """recovery owner cannot resume a journal after desired config changes."""
        td, root = make_root()
        try:
            run(root, "apply", owner="owner-a", fail_after="route_commit")
            config = cfg(root)
            config["subnets"][3]["cidr"] = "10.42.99.0/24"
            save_cfg(root, config)
            result, out = run(root, "resume", owner="owner-a")
            assert result.returncode != 0 and "config digest changed" in out["error"]
        finally:
            td.cleanup()

    def test_repeated_apply_is_idempotent(self):
        """running the full recovery twice does not duplicate moved actions or route associations."""
        td, root = make_root()
        try:
            run(root, "apply", owner="owner-a", check=True)
            first = state(root)
            first_journal = journal_lines(root)
            run(root, "apply", owner="owner-a", check=True)
            second = state(root)
            second_journal = journal_lines(root)
            assert first["moved"] == second["moved"]
            assert first["gateway_endpoints"] == second["gateway_endpoints"]
            assert first["route_tables"] == second["route_tables"]
            assert len(second_journal) == len(first_journal)
        finally:
            td.cleanup()

    def test_verify_reports_ready_after_full_recovery(self):
        """verify confirms the final recovered state generated by the controller."""
        td, root = make_root()
        try:
            result, out = run(root, "verify")
            assert result.returncode != 0 or out.get("phase") != "READY"
            assert out.get("valid") is not True

            run(root, "apply", owner="owner-a", check=True)
            _, out = run(root, "verify", check=True)
            assert out["valid"] is True and out["phase"] == "READY"
        finally:
            td.cleanup()

    def test_final_state_preserves_audit_endpoint_import_and_routing(self):
        """final recovery keeps all earlier routing, endpoint, import, and audit behavior."""
        td, root = make_root()
        try:
            run(root, "apply", owner="owner-a", check=True)
            recovered = state(root)
            assert recovered["flow_log"] and recovered["resolver_security_group"] and recovered["moved"]
            assert all(default_target(rt) is None for rt in data_rts(recovered))
            app = set(recovered["outputs"]["private_app_route_table_ids"])
            assert all(set(ep["route_table_ids"]) == app for ep in recovered["gateway_endpoints"])
        finally:
            td.cleanup()
