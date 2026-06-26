# ruff: noqa
"""Behavioral verification for sequence safety and durable readiness."""
from helpers import (
    apply_source,
    inspect,
    repair,
    replicate,
    reset,
    row,
    run,
    save_state,
    state,
    tx,
)

class TestMilestone3:
    def setup_method(self):
        reset()
        repair()

    def _ready_base(self):
        run("sync-sequences")
        return run("readiness")[1]

    def test_sequence_behind_target_data_is_advanced_exactly(self):
        """A lagging sequence advances to one greater than the current target maximum."""
        result=run("sync-sequences")[1]
        target=inspect("target")
        assert target["sequences"]["customer_profile_customer_id_seq"]==1003
        assert result["details"]["customer_profile_customer_id_seq"]["safe"]

    def test_sequence_already_ahead_remains_unchanged(self):
        """Synchronization preserves a sequence that is already safely ahead."""
        target=state("target-database.json")
        target["sequences"]["customer_profile_customer_id_seq"]=9000
        save_state("target-database.json",target)
        run("sync-sequences")
        assert inspect("target")["sequences"]["customer_profile_customer_id_seq"]==9000

    def test_sequence_never_moves_backward_after_row_removal(self):
        """Removing the previous maximum row cannot reduce a durable next value."""
        target=state("target-database.json")
        target["sequences"]["account_status_status_id_seq"]=8000
        target["tables"]["account_status"]=[target["tables"]["account_status"][0]]
        save_state("target-database.json",target)
        run("sync-sequences")
        assert inspect("target")["sequences"]["account_status_status_id_seq"]==8000

    def test_lag_below_policy_passes_when_exact_fence_is_reached(self):
        """A fully replayed fence with lag below policy becomes READY."""
        result=self._ready_base()
        assert result["valid"] and result["lag_bytes"]==0

    def test_lag_above_policy_blocks_readiness(self):
        """Source progress far beyond the subscriber position blocks READY."""
        t=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"Lagging"}}],delta=128)
        apply_source([t])
        run("sync-sequences")
        result=run("readiness")[1]
        assert not result["valid"] and "replication_lag_exceeds_policy" in result["reasons"]

    def test_target_must_reach_exact_cutover_fence(self):
        """A small lag inside the byte threshold still cannot satisfy the exact fence requirement."""
        t=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"Small Lag"}}],delta=16)
        apply_source([t])
        run("sync-sequences")
        result=run("readiness")[1]
        assert result["lag_bytes"]==16 and "target_not_at_exact_fence" in result["reasons"] and not result["valid"]

    def test_failed_replication_transaction_blocks_readiness(self):
        """A recorded failed transaction remains an explicit readiness blocker."""
        t=tx([{"op":"insert","table":"account_status","row":{"status_id":4901,"customer_id":1001,"status":"INVALID","changed_at":"2026-06-18T12:00:00Z"}}])
        apply_source([t])
        replicate()
        run("sync-sequences")
        result=run("readiness")[1]
        assert "failed_replication_transaction" in result["reasons"]

    def test_excessive_slot_retention_blocks_according_to_policy(self):
        """Retention above the contract block threshold prevents readiness."""
        run("sync-sequences")
        slot=state("replication-slot.json")
        slot["retained_wal_bytes"]=129
        save_state("replication-slot.json",slot)
        warning=run("readiness")[1]
        assert warning["valid"] and warning["warnings"]==["slot_retention_warning"]
        slot=state("replication-slot.json")
        slot["retained_wal_bytes"]=513
        save_state("replication-slot.json",slot)
        result=run("readiness")[1]
        assert not result["valid"] and "slot_retention_exceeds_policy" in result["reasons"]

    def test_source_progress_invalidates_stale_readiness(self):
        """A durable READY generation becomes invalid after a new source commit."""
        first=self._ready_base()
        t=tx([{"op":"update","table":"customer_profile","key":1002,"changes":{"display_name":"After Ready"}}])
        apply_source([t])
        second=run("readiness")[1]
        assert first["valid"] and not second["valid"] and second["generation"]>first["generation"]

    def test_restart_reconstructs_same_readiness_generation(self):
        """Controller restart reconstructs unchanged READY state without a new generation."""
        first=self._ready_base()
        run("restart-controller")
        second=run("readiness")[1]
        assert second==first

    def test_one_consistent_lsn_drives_every_readiness_component(self):
        """Source, target, subscriber, slot, and fence positions agree in a valid decision."""
        result=self._ready_base()
        assert len({result["fence_lsn"],result["source_lsn"],result["target_lsn"],result["subscription_lsn"],result["slot_flush_lsn"]})==1

    def test_repeated_readiness_check_is_idempotent(self):
        """An unchanged readiness check preserves generation and journal length."""
        first=self._ready_base()
        journal=inspect("journal")
        second=run("readiness")[1]
        assert second==first and inspect("journal")==journal
