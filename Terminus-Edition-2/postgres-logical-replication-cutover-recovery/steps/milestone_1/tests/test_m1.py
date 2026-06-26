# ruff: noqa
"""Behavioral verification for logical publication coverage."""
import json
from pathlib import Path
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

class TestMilestone1:
    def setup_method(self):
        reset()

    def test_all_required_business_tables_are_published(self):
        """Publication repair includes every business relation required by contract."""
        repaired=repair()
        contract=json.loads((APP/"config/publication-contract.yaml").read_text())
        assert set(repaired["tables"])==set(contract["required_tables"])

    def test_operational_tables_remain_excluded(self):
        """Operational heartbeat and probe relations never enter the publication."""
        repaired=repair()
        assert set(repaired["tables"]).isdisjoint({"migration_heartbeat","replication_probe"})
        t=tx([{"op":"insert","table":"migration_heartbeat","row":{"heartbeat_id":2,"observed_at":"2026-06-18T12:00:00Z"}},{"op":"update","table":"customer_profile","key":1001,"changes":{"display_name":"Business Change"}}])
        apply_source([t])
        replicate()
        assert row("target","migration_heartbeat","heartbeat_id",2) is None
        assert row("target","customer_profile","customer_id",1001)["display_name"]=="Business Change"

    def test_insert_replays_with_primary_key_identity(self):
        """A generated insert reaches the target under its source primary key."""
        repair()
        t=tx([{"op":"insert","table":"customer_profile","row":{"customer_id":1201,"display_name":"Generated Customer","middle_name":None,"email":"generated@example.test"}}])
        apply_source([t])
        replicate()
        assert row("target","customer_profile","customer_id",1201)["email"]=="generated@example.test"

    def test_update_replays_existing_row(self):
        """Published updates change the matching target row without creating a duplicate."""
        repair()
        t=tx([{"op":"update","table":"customer_profile","key":1001,"changes":{"email":"asha.updated@example.test"}}])
        apply_source([t])
        replicate()
        target=inspect("target")
        rows=[r for r in target["tables"]["customer_profile"]if r["customer_id"]==1001]
        assert len(rows)==1 and rows[0]["email"]=="asha.updated@example.test"

    def test_delete_replays_existing_row(self):
        """A published delete removes the corresponding target identity."""
        repair()
        t=tx([{"op":"delete","table":"contact_method","key":2002}])
        apply_source([t])
        replicate()
        assert row("target","contact_method","contact_id",2002) is None

    def test_multitable_transaction_is_atomic(self):
        """Parent, dependent, and audit operations share one durable replication transaction."""
        repair(); t=tx([
          {"op":"insert","table":"customer_profile","row":{"customer_id":1301,"display_name":"Atomic Parent","middle_name":None,"email":"atomic@example.test"}},
          {"op":"insert","table":"contact_method","row":{"contact_id":2301,"customer_id":1301,"kind":"email","value":"atomic.alt@example.test","verified_at":None}},
          {"op":"insert","table":"profile_audit","row":{"audit_id":5301,"customer_id":1301,"event_type":"PROFILE_CREATED","payload":"{}","created_at":"2026-06-18T12:00:00Z"}}])
        apply_source([t])
        replicate()
        target=inspect("target")
        assert row("target","customer_profile","customer_id",1301)
        assert row("target","contact_method","contact_id",2301)
        ledger=[x for x in target["transaction_ledger"] if x["transaction_id"]==t["transaction_id"]]
        assert ledger==[{"transaction_id":t["transaction_id"],"commit_lsn":t["commit_lsn"],"origin":"replication","operation_count":3}]

    def test_missing_replica_identity_fails_without_state_replacement(self):
        """Unsafe replica identity blocks repair while preserving publication and slot identity."""
        before_pub=inspect("publication")
        before_slot=inspect("slot")
        source=state("source-database.json")
        source["schema"]["tables"]["contact_method"]["replica_identity"]="none"
        save_state("source-database.json",source)
        cp,_=run("repair-publication",check=False)
        assert cp.returncode!=0
        assert inspect("publication")==before_pub
        assert inspect("slot")["creation_id"]==before_slot["creation_id"]

    def test_publication_repair_is_idempotent(self):
        """Repeating repair with no contract change leaves revision and journal stable."""
        first=repair()
        journal1=inspect("journal")
        second=repair()
        journal2=inspect("journal")
        assert second==first and journal2==journal1

    def test_publication_table_order_does_not_change_behavior(self):
        """Reordering the SQL table list does not create a new semantic revision."""
        first=repair()
        path=APP/"migration/publication.sql"
        original=path.read_text()
        try:
            path.write_text("CREATE PUBLICATION profile_migration_pub FOR TABLE profile_audit, contact_method, account_status, customer_profile, communication_preference WITH (publish = 'update, delete, insert');\n")
            second=repair()
        finally: path.write_text(original)
        assert second["revision"]==first["revision"]
        assert second["tables"]==first["tables"] and second["operations"]==first["operations"]

    def test_existing_slot_and_subscription_identity_remain_stable(self):
        """Repair and replay never replace the named slot or subscription."""
        slot=inspect("slot")
        sub=inspect("subscription")
        repair()
        t=tx([{"op":"update","table":"customer_profile","key":1002,"changes":{"display_name":"Stable Identity"}}])
        apply_source([t])
        replicate()
        assert inspect("slot")["creation_id"]==slot["creation_id"]
        assert inspect("slot")["name"]=="profile_migration_slot"
        assert inspect("subscription")["name"]==sub["name"] and inspect("subscription")["slot_name"]==sub["slot_name"]
