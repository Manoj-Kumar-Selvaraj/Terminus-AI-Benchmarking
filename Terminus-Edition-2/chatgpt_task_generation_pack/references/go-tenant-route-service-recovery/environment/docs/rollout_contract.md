# Rollout contract

The platform sends a termination signal before replacing a router instance. New
connections can stop immediately, but requests already accepted by the process
should finish if they remain inside the grace period.

This contract is intentionally stricter than a hard listener close because
tenant routing clients retry non-idempotent requests poorly.
