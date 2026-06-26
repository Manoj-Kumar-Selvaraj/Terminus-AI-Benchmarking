During a card-network peak, both warm signing nodes reached the HSM under different lease epochs. One node's wall clock was ahead, and the former owner continued signing after failover. Review `/app/evidence/failover_timeline.log`, `/app/docs/lease_contract.md`, `/app/docs/operator_runbook.md`, and the Java implementation under `/app/src`.

Restore coordinator-time lease acquisition, renewal, and fencing without removing the two-node failover model or serializing through an external service. Privileged commands must reject stale, tampered, and expired tokens. Acquisition must be atomic and deterministic when processes race, while same-owner reacquisition remains idempotent.

The verifier covers pre-expiry takeover, post-expiry epoch changes, stale former owners, renewal boundaries, same-owner reacquisition, token tampering, and simultaneous acquisition processes.
