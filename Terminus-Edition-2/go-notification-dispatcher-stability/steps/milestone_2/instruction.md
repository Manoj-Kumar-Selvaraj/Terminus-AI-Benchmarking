After backlog handling was repaired, rolling deployments still exceeded the 250 ms shutdown window and were force-killed. Calls arriving during termination also produced unstable behavior. Review `/app/evidence/shutdown_trace.log` and `/app/docs/shutdown_contract.md`. Make shutdown cancellation-aware, repeatable, and safe when it races with producers while preserving all milestone 1 behavior.

The verifier runs in-flight cancellation, repeated shutdown, post-shutdown enqueue, queue-depth cleanup, and concurrent enqueue/shutdown scenarios under the race detector.
