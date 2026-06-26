# Cutover contract

Readiness is valid only for one captured source LSN and one durable readiness generation. Coverage, schema, sequences, lag, failed transactions, exact target replay, and slot retention are evaluated against that same capture. Source progress invalidates an older READY decision.

The durable cutover phases are `READY -> SOURCE_FENCING -> SOURCE_FENCED -> FINAL_REPLICATION_DRAIN -> TARGET_VALIDATED -> TARGET_ENABLED -> CUTOVER_COMMITTED`. The source fence is durable before target activation. At no durable observation may both clusters accept writes. Retries use a stable operation ID and return the stored result after commit.
