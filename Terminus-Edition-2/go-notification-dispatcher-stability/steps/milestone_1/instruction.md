During the statement-completion surge, the dispatcher stopped making enqueue progress even though delivery latency remained low and all workers were still allocated. Review `/app/evidence/goroutine_dump.txt`, `/app/evidence/queue_depth.log`, `/app/config/workers.json`, and `/app/docs/dispatcher_contract.md`. Restore bounded producer progress and accurate queue-depth accounting without removing the fixed worker pool, spawning a goroutine per job, or changing the exported dispatch API.

When the bounded queue is full, `Enqueue` must block the calling goroutine until space is available instead of returning a fail-fast error or spinning. Do not hold the dispatcher mutex while waiting for queue capacity.

The verifier exercises concurrent bursts, configured queue capacity, worker-concurrency bounds, blocking backpressure, invalid-job handling, and eventual queue drainage under the race detector.
