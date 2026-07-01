# Offline failure-injection fields

These fields exist only for deterministic local verification. They are ignored as business data.

| Body field | Effect |
| --- | --- |
| `fixture_delay_ms` | Delays this record before persistence, allowing completion order to differ from input order. Values are capped by the fixture runtime. |
| `fixture_infrastructure_failure` | Raises an unexpected dependency error. The invocation must fail; it is not a classified item failure. |
| `fixture_crash_after_journal_commit` | Exits with code `86` after durable journal append but before ledger replacement. |
| `fixture_crash_during_ledger_replace` | Exits with code `87` after writing and syncing the replacement file but before rename. |
| `fixture_crash_after_commit` | Exits with code `88` after the flat ledger has been atomically committed but before acknowledgement. |

`SIMULATOR_CRASH_POINT=after_dlq_append` exits the replay process with a nonzero status after a DLQ row is durably appended but before source retirement is checkpointed. Like the Node fixture crash codes `86` through `88`, this is a required crash signal rather than a successful replay. A later invocation must converge without a second DLQ row or redelivery.

`DELIVERY_STATE` may override the replay checkpoint path. If omitted while `DLQ_STATE` is set, the checkpoint lives beside the DLQ file with suffix `.delivery.json`. Receive counts and retired-message state must survive separate simulator processes.
