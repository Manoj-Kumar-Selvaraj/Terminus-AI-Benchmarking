# Journal recovery contract

Controller state lives under the operator-supplied state directory. `journal.jsonl` is append-only JSON Lines. A complete malformed line is corruption: commands must fail, must not truncate the journal, and must not create a recovery artifact.

A process crash may leave only the final record incomplete, with malformed bytes after the last valid newline. On the first subsequent read, the controller must:

1. preserve the exact incomplete bytes at `recovery/torn-tail.bin` using a durable atomic write;
2. retain the byte-identical valid prefix in `journal.jsonl` and truncate only the incomplete suffix;
3. reconstruct all valid earlier state and continue normal operation;
4. make repeated reads and restarts idempotent, without additional recovery files or further mutation.

A syntactically valid final record is valid even when it lacks a trailing newline. Empty trailing lines are ignored. Journal repair must never delete accepted rollout history or replace the whole state directory.
