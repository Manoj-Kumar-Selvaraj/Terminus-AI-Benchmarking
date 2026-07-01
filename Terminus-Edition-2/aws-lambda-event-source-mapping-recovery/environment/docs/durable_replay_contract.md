# Durable replay and ledger sidecars

The handler keeps the ledger as a flat JSON array. `business_event_id` is the durable idempotency key. Replays for the same business event commit one row, preserve the original primary `message_id`, and append alternate message IDs to `duplicate_message_ids` in first successful observation order. The alternate list excludes the primary ID and remains unique.

Sidecar paths are derived from `SIDE_EFFECT_LEDGER`: the journal is `SIDE_EFFECT_LEDGER + ".journal"` and the lock is `SIDE_EFFECT_LEDGER + ".lock"`. The lock file is JSON with `pid` and `created_ms`. A lock from a dead process may be reclaimed.

The journal is JSON lines. Complete records contain `seq`, `snapshot`, and `checksum`. A complete journal record remains on disk after a successful ledger commit; recovery uses it as committed evidence, not as a temporary file to delete after the flat ledger is replaced.

The checksum is `SHA-256` hex over the UTF-8 bytes of the compact insertion-order JSON object `{"seq":<seq>,"snapshot":<snapshot>}` rendered with comma and colon separators and no extra spaces. This is the same byte shape produced by JavaScript `JSON.stringify({ seq, snapshot })`: do not sort keys, and preserve the existing insertion order of nested `snapshot` objects. A truncated final line is uncommitted tail data and may be ignored. A complete line with a bad checksum is committed corruption and must fail closed without treating the ledger as empty.

Crash injection is deterministic. `fixture_crash_after_journal_commit` exits with code `86` after the journal append. `fixture_crash_during_ledger_replace` exits with code `87` after the replacement file is written and synced but before rename. `fixture_crash_after_commit` exits with code `88` after the ledger commit but before acknowledgement. Each crash exits nonzero and leaves enough durable state for a retry to converge.

`DLQ_STATE` and `DELIVERY_STATE` define replay checkpoint paths. Receive counts and retired-message state must be written to the delivery-state checkpoint after replay decisions so they survive separate simulator process invocations. If `DELIVERY_STATE` is omitted while `DLQ_STATE` is set, the delivery checkpoint lives beside the DLQ file with suffix `.delivery.json`. Keeping receive counts only in process memory is not sufficient. Poison and malformed records move to the configured DLQ at exactly `max_receive_count`, append exactly once, and then stop being delivered.

`SIMULATOR_CRASH_POINT=after_dlq_append` exits the simulator replay process with a nonzero status after the DLQ row is durable but before source-message retirement is checkpointed. A later replay must converge to one DLQ row, no duplicate append, and no continued redelivery for that source message.
