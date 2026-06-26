# Dispatcher Contract

The billing-alert dispatcher uses a fixed-size worker pool. The public API under
`internal/dispatch` is already consumed by `cmd/notifierd` and must remain source compatible.

## Queue and worker guarantees

- `NewDispatcher(n, deliver)` starts exactly `n` delivery workers when `n > 0`.
- The queue capacity is `worker_count * queue_buffer_multiplier`; the supplied configuration uses a multiplier of 4.
- `Enqueue` validates that `OperationKey` is non-empty and blocks the calling goroutine until queue space is available when the bounded backlog is full.
- No mutex may be held while waiting for queue capacity.
- Delivery concurrency must never exceed the configured worker count. Spawning one goroutine per job is not an acceptable remediation.
- `QueueDepth` represents accepted jobs that have not yet been handed to a worker and must eventually return to zero after the backlog drains.

## Compatibility

Keep the exported `NewDispatcher`, `Enqueue`, `QueueDepth`, `Shutdown`, `Context`, `Job`, and `DeliverFunc` contracts intact.
