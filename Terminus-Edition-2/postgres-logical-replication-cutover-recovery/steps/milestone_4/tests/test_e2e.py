# ruff: noqa
"""Cumulative end-to-end migration incident scenarios."""
from helpers import (
    APP,
    apply_source,
    inspect,
    prepare_ready,
    repair,
    replicate,
    reset,
    row,
    run,
    save_state,
    state,
    tx,
)

class TestEndToEnd:
    def test_scenario_a_successful_online_migration(self):
        """Logical replay, validation, sequence sync, fence, drain, and activation complete in order."""
        reset()
        repair()
        run("apply-source","--file",str(APP/"data/change-stream.jsonl"))
        assert replicate()["status"] == "ok"
        assert run("validate-schema")[1]["valid"] and run("sync-sequences")[1]["valid"] and run("readiness")[1]["valid"]
        result=run("cutover","--operation-id","e2e-success")[1]
        assert result["status"]=="committed" and not inspect("source")["writable"] and inspect("target")["writable"]

    def test_scenario_b_missing_publication_table_blocks_cutover(self):
        """A required relation removed from publication invalidates readiness and cutover."""
        reset()
        repair()
        pub=state("publication-state.json")
        pub["tables"].remove("communication_preference")
        save_state("publication-state.json",pub)
        run("sync-sequences")
        ready=run("readiness")[1]
        cp,_=run("cutover","--operation-id","e2e-missing",check=False)
        assert not ready["valid"] and "replication_coverage_invalid" in ready["reasons"] and cp.returncode!=0

    def test_scenario_c_schema_incompatibility_is_atomic(self):
        """An incompatible status transaction applies neither parent change nor audit side effect."""
        reset()
        repair()
        t=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"No Partial"}},{"op":"insert","table":"account_status","row":{"status_id":4990,"customer_id":1001,"status":"UNKNOWN","changed_at":"2026-06-18T12:00:00Z"}}])
        apply_source([t])
        replicate()
        run("sync-sequences")
        ready=run("readiness")[1]
        assert row("target","customer_profile","customer_id",1001)["display_name"]=="Asha Rao" and not ready["valid"]

    def test_scenario_d_sequence_collision_risk_is_removed(self):
        """Target-generated identities start beyond all replicated primary keys."""
        reset()
        repair()
        result=run("sync-sequences")[1]
        assert result["valid"] and all(x["current"]==x["required_minimum"] for x in result["details"].values())

    def test_scenario_e_restart_after_source_fence_is_safe(self):
        """Restart after source fencing resumes without a dual-writer interval."""
        prepare_ready()
        run("inject-failure","--point","AFTER_WRITE_FENCE")
        run("cutover","--operation-id","e2e-restart",check=False)
        run("restart-controller")
        run("cutover","--operation-id","e2e-restart")
        assert not inspect("source")["writable"] and inspect("target")["writable"]
        assert all(not (x.get("source_writable") and x.get("target_writable")) for x in inspect("journal") if x.get("operation_id")=="e2e-restart")

    def test_scenario_f_lost_response_reuses_committed_result(self):
        """Retry after a lost commit response returns the stored operation result."""
        prepare_ready()
        run("inject-failure","--point","AFTER_CUTOVER_JOURNAL")
        run("cutover","--operation-id","e2e-lost",check=False)
        before=inspect("journal")
        result=run("cutover","--operation-id","e2e-lost")[1]
        assert result["result"]["operation_id"]=="e2e-lost" and inspect("journal")==before

    def test_scenario_g_rollback_transfers_limited_target_writes_once(self):
        """Target-only writes are reverse-applied once while replicated source history is not replayed."""
        prepare_ready(with_fixture=True)
        run("cutover","--operation-id","e2e-rb")
        run("apply-target","--file",str(APP/"data/rollback-writes.jsonl"))
        run("rollback","--operation-id","e2e-rollback","--cutover-operation-id","e2e-rb")
        source=inspect("source")
        assert row("source", "contact_method", "contact_id", 2100)
        assert len([x for x in source["transaction_ledger"] if x["transaction_id"]=="txn-target-only-001"])==1
        assert not any(x.get("origin")=="rollback" and x["transaction_id"].startswith("txn-profile-update") for x in source["transaction_ledger"])

    def test_scenario_h_repeated_completed_workflow_is_stable(self):
        """Completed cutover and rollback retries preserve transactions, positions, slot, and journals."""
        prepare_ready()
        slot=inspect("slot")
        run("cutover","--operation-id","e2e-repeat")
        run("rollback","--operation-id","e2e-repeat-rb","--cutover-operation-id","e2e-repeat")
        snapshot={"source":inspect("source"),"target":inspect("target"),"slot":inspect("slot"),"subscription":inspect("subscription"),"cutover":inspect("cutover"),"journal":inspect("journal")}
        run("cutover","--operation-id","e2e-repeat",check=False)
        run("rollback","--operation-id","e2e-repeat-rb","--cutover-operation-id","e2e-repeat")
        assert inspect("source")==snapshot["source"] and inspect("target")==snapshot["target"] and inspect("journal")==snapshot["journal"]
        assert inspect("slot")==snapshot["slot"] and inspect("slot")["creation_id"]==slot["creation_id"]
        assert sum(1 for x in inspect("journal") if x.get("event_id")=="cutover:e2e-repeat:CUTOVER_COMMITTED")==1
