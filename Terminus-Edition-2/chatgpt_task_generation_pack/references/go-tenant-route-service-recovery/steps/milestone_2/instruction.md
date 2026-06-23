After the route refresh failure was stabilized, the same request path still caused resource growth during repeated upstream failures. Review `/app/evidence/goroutine_summary.txt` and `/app/docs/upstream_contract.md`. Restore repeated upstream-error handling so the router does not retain resources after each failed proxy attempt.

Preserve the milestone 1 refresh and lookup guarantees. Successful upstream responses should continue to be returned to callers, and upstream 5xx responses should remain gateway errors rather than being reported as tenant-route misses.
