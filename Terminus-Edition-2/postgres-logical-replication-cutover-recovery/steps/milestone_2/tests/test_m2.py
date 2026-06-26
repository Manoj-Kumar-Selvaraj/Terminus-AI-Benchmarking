# ruff: noqa
"""Behavioral verification for schema-safe transactional replay."""
from helpers import (
    APP,
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

class TestMilestone2:
    def setup_method(self):
        reset()
        repair()

    def test_explicit_null_is_preserved(self):
        """An explicit source null remains null in the target row."""
        t=tx([{"op":"insert","table":"communication_preference","row":{"preference_id":3101,"customer_id":1001,"channel":"sms","enabled":True,"quiet_hours_start":None,"quiet_hours_end":None}}])
        apply_source([t])
        replicate()
        assert row("target","communication_preference","preference_id",3101)["quiet_hours_start"] is None

    def test_target_default_does_not_replace_replicated_null(self):
        """Target defaults are not substituted when a nullable value is explicitly transmitted."""
        path=APP/"migration/target_schema.sql"
        original=path.read_text()
        try:
            path.write_text(original.replace("quiet_hours_start TEXT,","quiet_hours_start TEXT DEFAULT '00:00',"))
            t=tx([{"op":"insert","table":"communication_preference","row":{"preference_id":3201,"customer_id":1001,"channel":"push","enabled":True,"quiet_hours_start":None,"quiet_hours_end":None}}])
            apply_source([t])
            replicate()
            assert row("target","communication_preference","preference_id",3201)["quiet_hours_start"] is None
        finally: path.write_text(original)

    def test_compatible_character_widening_is_accepted(self):
        """A source-valid value longer than the old target width replays without truncation."""
        value="N"*110
        t=tx([{"op":"insert","table":"customer_profile","row":{"customer_id":1401,"display_name":value,"middle_name":None,"email":"wide@example.test"}}])
        apply_source([t])
        replicate()
        assert row("target","customer_profile","customer_id",1401)["display_name"]==value

    def test_incompatible_narrowing_is_rejected(self):
        """Narrowing the target below the source contract makes schema validation fail."""
        path=APP/"migration/target_schema.sql"
        original=path.read_text()
        try:
            path.write_text(original.replace("display_name VARCHAR(160)","display_name VARCHAR(20)"))
            result=run("validate-schema")[1]
        finally: path.write_text(original)
        assert not result["valid"] and "narrowing:customer_profile.display_name" in result["errors"]

    def test_unknown_status_is_rejected_atomically(self):
        """An undocumented status value blocks the whole transaction."""
        t=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"Must Roll Back"}},{"op":"insert","table":"account_status","row":{"status_id":4401,"customer_id":1001,"status":"MYSTERY","changed_at":"2026-06-18T12:00:00Z"}}])
        apply_source([t])
        result=replicate()
        assert result["status"]=="blocked"
        assert row("target","customer_profile","customer_id",1001)["display_name"]=="Asha Rao"
        assert row("target","account_status","status_id",4401) is None

    def test_parent_and_child_commit_together(self):
        """A child listed before its new parent becomes visible only with the committed parent."""
        t=tx([{"op":"insert","table":"customer_profile","row":{"customer_id":1501,"display_name":"Atomic Parent","middle_name":None,"email":"parent@example.test"}},{"op":"insert","table":"contact_method","row":{"contact_id":2501,"customer_id":1501,"kind":"email","value":"child@example.test","verified_at":None}}])
        apply_source([t])
        result=replicate()
        assert result["status"]=="ok" and row("target","customer_profile","customer_id",1501) and row("target","contact_method","contact_id",2501)

    def test_failed_child_rolls_back_parent_operation(self):
        """A dependent-row failure leaves no parent subset visible on the target."""
        target=state("target-database.json")
        target["tables"]["contact_method"].append({"contact_id":2601,"customer_id":1001,"kind":"email","value":"preexisting-target@example.test","verified_at":None})
        save_state("target-database.json",target)
        t=tx([{"op":"insert","table":"customer_profile","row":{"customer_id":1601,"display_name":"Rollback Parent","middle_name":None,"email":"rollback@example.test"}},{"op":"insert","table":"contact_method","row":{"contact_id":2601,"customer_id":1601,"kind":"email","value":"new-child@example.test","verified_at":None}}])
        apply_source([t])
        replicate()
        assert row("target","customer_profile","customer_id",1601) is None
        existing=row("target","contact_method","contact_id",2601)
        assert existing["customer_id"]==1001 and existing["value"]=="preexisting-target@example.test"

    def test_audit_rows_remain_immutable(self):
        """Update or delete operations against append-only audit history reject the transaction."""
        before=row("target","profile_audit","audit_id",5001).copy()
        t=tx([{"op":"update","table":"profile_audit","key":5001,"changes":{"payload":"tampered"}}])
        apply_source([t])
        replicate()
        assert row("target","profile_audit","audit_id",5001)==before
        assert inspect("subscription")["failed_transactions"][0]["transaction_id"]==t["transaction_id"]

    def test_schema_version_mismatch_blocks_replay_and_readiness(self):
        """A transaction from an incompatible schema version is not applied and remains a readiness blocker."""
        t=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"Version Four"}}],schema_version=4)
        apply_source([t])
        replicate()
        result=run("readiness")[1]
        assert row("target","customer_profile","customer_id",1001)["display_name"]=="Asha Rao"
        assert not result["valid"]

    def test_long_value_is_not_silently_truncated(self):
        """A value beyond the compatible target width rejects the transaction rather than truncating it."""
        value="X"*200
        t=tx([{"op":"insert","table":"customer_profile","row":{"customer_id":1701,"display_name":value,"middle_name":None,"email":"long@example.test"}}])
        apply_source([t])
        replicate()
        assert row("target","customer_profile","customer_id",1701) is None

    def test_repeated_schema_validation_is_deterministic(self):
        """Repeated validation of unchanged SQL and contracts returns identical structured results."""
        first=run("validate-schema")[1]
        second=run("validate-schema")[1]
        assert first==second=={"valid":True,"source_version":3,"target_version":3,"errors":[]}
