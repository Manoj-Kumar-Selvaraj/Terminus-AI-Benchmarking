# Runbook excerpt

Use `/healthz` for platform health checks. A route refresh should be safe while
traffic is flowing; it replaces the active tenant upstream set.

During termination, send SIGTERM and allow in-flight requests to complete inside
the platform's grace period. Do not close accepted connections simply because a
new rollout has started.
