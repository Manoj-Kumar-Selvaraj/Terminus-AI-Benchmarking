# Replay runbook note

Replay runs should be idempotent. A restart may reuse a fixture file, but already committed business events must not produce duplicate ledger rows. Poison messages are expected to fail closed and move to the configured DLQ after max receives.
