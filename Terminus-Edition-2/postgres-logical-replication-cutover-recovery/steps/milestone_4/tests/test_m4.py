# ruff: noqa
"""Behavioral verification for recoverable writer cutover and rollback."""
import concurrent.futures
from helpers import (
    apply_source,
    apply_target,
    inspect,
    prepare_ready,
    repair,
    reset,
    row,
    run,
    state,
    tx,
    write_stream,
)

class TestMilestone4:
    def setup_method(self):
        prepare_ready()

    def test_successful_cutover_activates_only_target(self):
        """A successful cutover commits with the new cluster as the sole writer."""
        result=run("cutover","--operation-id","cutover-success")[1]
        assert result["status"]=="committed"
        assert not inspect("source")["writable"] and inspect("target")["writable"]

    def test_source_fence_precedes_target_enablement(self):
        """Durable phase history records source fencing before target activation."""
        run("cutover","--operation-id","cutover-order")
        phases=[x["phase"] for x in inspect("journal") if x.get("operation_id")=="cutover-order"]
        assert phases.index("SOURCE_FENCED")<phases.index("TARGET_ENABLED")<phases.index("CUTOVER_COMMITTED")

    def test_no_durable_phase_has_two_writers(self):
        """Every cutover journal snapshot respects the single-writer invariant."""
        pending=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"Concurrent Source Write"}}])
        stream=write_stream([pending])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            write_future=pool.submit(run,"apply-source","--file",stream,check=False)
            cutover_future=pool.submit(run,"cutover","--operation-id","cutover-writers",check=False)
            write_result=write_future.result()
            cutover_result=cutover_future.result()
        source=inspect("source")
        target=inspect("target")
        assert source["writable"] != target["writable"]
        assert not (source["writable"] and target["writable"])
        assert (write_result[0].returncode==0) != (cutover_result[0].returncode==0)
        rows=[x for x in inspect("journal") if x.get("operation_id")=="cutover-writers"]
        assert all(not (x["source_writable"] and x["target_writable"]) for x in rows)

    def test_failure_before_source_fence_leaves_source_active(self):
        """Failure before fencing cannot accidentally disable the only writer."""
        t=tx([{"op":"update","table":"customer_profile","key":1002,"changes":{"display_name":"Stale Readiness"}}])
        apply_source([t])
        cp,_=run("cutover","--operation-id","cutover-stale",check=False)
        assert cp.returncode!=0 and inspect("source")["writable"] and not inspect("target")["writable"]
        prepare_ready()
        run("inject-failure","--point","BEFORE_SOURCE_FENCE")
        cp,_=run("cutover","--operation-id","cutover-before",check=False)
        assert cp.returncode!=0 and inspect("source")["writable"] and not inspect("target")["writable"]

    def test_failure_after_source_fence_resumes_same_operation(self):
        """Retry after a durable source fence resumes rather than starting another cutover."""
        run("inject-failure","--point","AFTER_WRITE_FENCE")
        cp,_=run("cutover","--operation-id","cutover-fenced",check=False)
        assert cp.returncode!=0 and not inspect("source")["writable"] and not inspect("target")["writable"]
        result=run("cutover","--operation-id","cutover-fenced")[1]
        assert result["status"]=="committed" and inspect("target")["writable"]

    def test_failure_during_final_drain_resumes_from_durable_phase(self):
        """A drain failure preserves the fence and completes on same-ID retry."""
        run("inject-failure","--point","DURING_FINAL_DRAIN")
        cp,_=run("cutover","--operation-id","cutover-drain",check=False)
        assert cp.returncode!=0 and inspect("cutover")["phase"]=="FINAL_REPLICATION_DRAIN"
        assert run("cutover","--operation-id","cutover-drain")[1]["status"]=="committed"

    def test_failures_after_validation_or_enable_follow_recorded_recovery(self):
        """Failures around activation resume from TARGET_VALIDATED or TARGET_ENABLED without reopening source."""
        run("inject-failure","--point","AFTER_TARGET_VALIDATION")
        cp,_=run("cutover","--operation-id","cutover-validation",check=False)
        assert cp.returncode!=0 and inspect("cutover")["phase"]=="TARGET_VALIDATED" and not inspect("source")["writable"] and not inspect("target")["writable"]
        run("cutover","--operation-id","cutover-validation")
        reset()
        repair()
        run("sync-sequences")
        run("readiness")
        run("inject-failure","--point","AFTER_TARGET_ENABLE")
        cp,_=run("cutover","--operation-id","cutover-enabled",check=False)
        assert cp.returncode!=0 and inspect("cutover")["phase"]=="TARGET_ENABLED" and not inspect("source")["writable"] and inspect("target")["writable"]
        assert run("cutover","--operation-id","cutover-enabled")[1]["status"]=="committed"

    def test_lost_cutover_response_returns_existing_commit(self):
        """A response lost after durable commit does not repeat cutover effects."""
        run("inject-failure","--point","AFTER_CUTOVER_JOURNAL")
        cp,_=run("cutover","--operation-id","cutover-lost",check=False)
        assert cp.returncode!=0 and inspect("cutover")["phase"]=="CUTOVER_COMMITTED"
        before=inspect("journal")
        result=run("cutover","--operation-id","cutover-lost")[1]
        assert result["status"]=="committed" and inspect("journal")==before

    def test_controller_restart_resumes_cutover(self):
        """Restart after fencing reloads durable state and completes the same operation."""
        run("inject-failure","--point","AFTER_WRITE_FENCE")
        run("cutover","--operation-id","cutover-restart",check=False)
        run("restart-controller")
        result=run("cutover","--operation-id","cutover-restart")[1]
        assert result["status"]=="committed" and inspect("cutover")["cutover"]["operation_id"]=="cutover-restart"

    def test_pre_activation_rollback_safely_reopens_source(self):
        """An attempt abandoned before target activation can restore the old writer safely."""
        run("inject-failure","--point","AFTER_WRITE_FENCE")
        run("cutover","--operation-id","cutover-abandon",check=False)
        result=run("rollback","--operation-id","rollback-abandon","--cutover-operation-id","cutover-abandon")[1]
        assert result["status"]=="committed" and inspect("source")["writable"] and not inspect("target")["writable"]

    def test_rollback_transfers_target_only_write_once(self):
        """Rollback reverse-applies a target-origin transaction exactly once."""
        run("cutover","--operation-id","cutover-rb")
        target_tx=tx([{"op":"insert","table":"contact_method","row":{"contact_id":2801,"customer_id":1001,"kind":"phone","value":"+15550002801","verified_at":None}}],txid="target-only-2801")
        target_tx.pop("commit_lsn")
        apply_target([target_tx])
        run("rollback","--operation-id","rollback-rb","--cutover-operation-id","cutover-rb")
        source=inspect("source")
        assert row("source", "contact_method", "contact_id", 2801)
        assert [x for x in source["transaction_ledger"] if x["transaction_id"]=="target-only-2801"]==[{"transaction_id":"target-only-2801","origin":"rollback","cutover_operation_id":"cutover-rb"}]

    def test_conflicting_rollback_operation_id_is_rejected(self):
        """A different rollback ID cannot replace a completed rollback identity."""
        run("cutover","--operation-id","cutover-conflict")
        run("rollback","--operation-id","rollback-one","--cutover-operation-id","cutover-conflict")
        cp,_=run("rollback","--operation-id","rollback-two","--cutover-operation-id","cutover-conflict",check=False)
        assert cp.returncode!=0

    def test_repeated_cutover_is_idempotent(self):
        """Retrying a completed cutover returns the same object with no new journal records."""
        first=run("cutover","--operation-id","cutover-repeat")[1]
        journal=inspect("journal")
        second=run("cutover","--operation-id","cutover-repeat")[1]
        assert second==first and inspect("journal")==journal

    def test_repeated_rollback_is_idempotent(self):
        """Retrying a completed rollback does not replay writes or grow its journal."""
        run("cutover","--operation-id","cutover-rbrepeat")
        first=run("rollback","--operation-id","rollback-repeat","--cutover-operation-id","cutover-rbrepeat")[1]
        source=inspect("source")
        journal=inspect("journal")
        second=run("rollback","--operation-id","rollback-repeat","--cutover-operation-id","cutover-rbrepeat")[1]
        assert second==first and inspect("source")==source and inspect("journal")==journal
