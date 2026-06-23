# Shutdown Contract

During a rolling deployment, the platform calls `Shutdown(ctx)` and supplies a 250 ms deadline.

Required behavior:

1. The dispatcher stops accepting new jobs once shutdown begins.
2. In-flight deliveries receive the dispatcher cancellation context so interruptible work can return promptly.
3. Calls to `Enqueue` racing with shutdown must return normally; they must never panic because a shared channel was closed.
4. Repeated `Shutdown` calls are safe and wait on the same worker termination event.
5. `Shutdown` returns `nil` when workers exit before the caller deadline, otherwise it returns the caller context error.
6. Queue-depth telemetry is zero after a completed shutdown because queued-but-not-started work has been abandoned by the cancelled deployment.

The jobs channel is an internal implementation detail. A solution may close it only if concurrent senders are coordinated safely; cancellation without channel closure is also valid.
