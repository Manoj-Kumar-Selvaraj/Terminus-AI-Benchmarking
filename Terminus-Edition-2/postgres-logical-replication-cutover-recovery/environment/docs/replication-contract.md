# Logical replication contract

The publication is `profile_migration_pub`, the subscription is `profile_migration_sub`, and the existing slot is `profile_migration_slot`. The five customer business tables are replicated for inserts, updates, and deletes. `migration_heartbeat` and `replication_probe` are operational tables and must remain outside the publication.

A source transaction is the indivisible replay unit. Its `transaction_id`, `commit_lsn`, `commit_timestamp`, `source_epoch`, and ordered `operations` travel together. A transaction that cannot be safely replayed must leave no target-visible subset. Published update/delete operations require the replica identity declared by `/app/config/publication-contract.yaml`. Repairing publication metadata must not replace the subscription or slot.
