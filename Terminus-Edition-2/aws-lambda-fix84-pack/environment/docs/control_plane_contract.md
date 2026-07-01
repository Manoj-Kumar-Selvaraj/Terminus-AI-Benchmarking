# Local deployment-controller contract

The files in `/app/config/event_source_mapping.json` and `/app/config/lambda_role_policy.json` are generated runtime artifacts. Every invocation of `/app/scripts/run_simulation.py` first runs the local deployment controller under `/app/control_plane`, so direct edits to those two generated files are not durable repairs.

Mapping authority is generation based. Only records whose phase is `completed` or `active` are authoritative, and the highest authoritative generation wins. An older `rollback_pending` checkpoint is diagnostic state, not permission to overwrite a newer completed promotion. Reconciliation must be deterministic and idempotent: repeated runs with unchanged inputs produce byte-identical generated JSON.

Queue and alias values are references, not constants copied into controller code. Changing `expected_active_queue_arn` or the active alias manifest in an isolated workspace must change the rendered mapping and policy without source edits.

The runtime role policy is synthesized from the base policy and the single highest-generation grant whose status is `active`. The renderer preserves unrelated base statements and renders one queue statement for that active grant. It must not retain stale grants or discard actions while normalizing them.
