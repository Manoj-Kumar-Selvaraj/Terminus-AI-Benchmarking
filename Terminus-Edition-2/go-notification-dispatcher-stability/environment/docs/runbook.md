# Notification Dispatcher Runbook

1. Confirm `/healthz` responds on the dispatcher port.
2. Inspect `/app/evidence/queue_depth.log` for rising backlog during spikes.
3. Capture goroutine dump if producers report enqueue stalls.
4. During deploy, watch shutdown duration against `/app/docs/shutdown_contract.md`.
5. Compare duplicate delivery reports with `/app/evidence/duplicate_delivery.log`.
6. For legacy tenant rejections, diff failing body against `/app/samples/legacy_webhook_request.json`.

Primary code paths:

- `/app/internal/dispatch/` — worker pool and enqueue
- `/app/internal/delivery/` — webhook POST and payload formatting
- `/app/internal/idempotency/` — delivery ledger
