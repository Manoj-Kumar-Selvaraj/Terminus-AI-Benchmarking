# Compatibility requirements

Preserve cluster names, table names, primary keys, publication/subscription/slot identities, transaction JSON schema, audit immutability, cutover and rollback state schemas, and the operational-table exclusions. The public entry points are `/app/cmd/migration-controller/main.py` and `/opt/task-tools/pg-repl-runtime`.

Do not replace logical replay with a source-to-target snapshot copy, reset the state directory, recreate the slot, fabricate READY/CUTOVER state, or alter protected evidence, seed data, simulator files, or their hash manifests.
