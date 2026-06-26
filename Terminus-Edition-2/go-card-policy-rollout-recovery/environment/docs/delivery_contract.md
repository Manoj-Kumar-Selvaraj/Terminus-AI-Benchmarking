# Delivery and gateway contract

Each rollout-region pair has one stable delivery identity for its entire lifetime, including crashes, retries, process restarts, and compaction. A controller retry must send the same `command_id` and the same rollout content. Generating a fresh identity for each attempt is not compatible with the gateway audit contract.

The controller sends this JSON to `POST /v1/policies/apply`:

```json
{
  "command_id": "stable delivery identity",
  "rollout_id": "operator rollout id",
  "generation": 42,
  "policy_sha256": "lowercase SHA-256 of the policy bytes",
  "policy": "the original JSON policy bytes"
}
```

A gateway persists `active_generation`, `policy_sha256`, a monotonically increasing application `sequence`, the result for every seen command, request-attempt counts, and an audit entry for each actual activation. Repeating a seen command returns its original result and does not append another activation audit. An older generation returns HTTP 409 with status `stale`; the controller records that delivery as `superseded`, not `acked` or endlessly retryable. The same generation with a different digest returns `conflict` and remains a failed delivery. A successful `applied` or `already-active` response is recorded as `acked`.

The `after-apply` failpoint models the remote gateway durably applying a command before the controller writes its local acknowledgement. Restarting dispatch must converge to one gateway activation audit and an acknowledged local delivery without deleting either side's state.
