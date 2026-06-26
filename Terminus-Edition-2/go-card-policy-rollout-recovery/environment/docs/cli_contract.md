# CLI contract

## Build

Run `/app/scripts/build.sh`. It must produce the Go binaries `/app/bin/rolloutctl` and `/app/bin/gatewayd`.

## Enqueue

```text
/app/bin/rolloutctl enqueue \
  --state STATE_DIR \
  --rollout ROLLOUT_ID \
  --generation POSITIVE_INTEGER \
  --policy POLICY_JSON_FILE \
  --regions REGION[,REGION...]
```

The policy file must contain valid JSON. Enqueuing the same rollout identifier with the same generation, policy bytes, and regions is idempotent. Reusing an identifier for different content is rejected without changing durable state.

## Dispatch

```text
/app/bin/rolloutctl dispatch \
  --state STATE_DIR \
  --gateways GATEWAY_MAP_JSON \
  --workers POSITIVE_INTEGER \
  --worker-id ID \
  --now-unix UNIX_SECONDS \
  [--failpoint after-claim[:REGION]|after-apply[:REGION]]
```

The gateway map is a JSON object from region to base URL. Regions absent from the map remain pending while mapped regions may progress. `--now-unix` is the controller's logical clock for leases. Failpoints are part of the local incident simulator: `after-claim` exits with 85 and `after-apply` exits with 86.

## Status

```text
/app/bin/rolloutctl status --state STATE_DIR
```

Status writes JSON with `schema_version`, a generation-ordered `rollouts` array, and `active_generation` by region. Each rollout contains `id`, `generation`, `policy_sha256`, and region-sorted deliveries. Delivery records expose `region`, stable `command_id`, `status`, and any lease, claim-token, gateway-sequence, or last-error observations that exist. Status values are `pending`, `claimed`, `acked`, `superseded`, or `failed`.

## Compact

```text
/app/bin/rolloutctl compact --state STATE_DIR [--failpoint after-snapshot-rename]
```

Compaction must be restart-safe and preserve all observable rollout and delivery history. The compaction failpoint exits with 87 after the replacement snapshot is durable but before old journal bytes are removed.
