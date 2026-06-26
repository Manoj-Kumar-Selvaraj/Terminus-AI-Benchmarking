The idempotent retry rollout exposed a compatibility regression for client `legacy-v1`: the initial request used its flat schema, but a retry used the modern envelope and was rejected. Review `/app/evidence/legacy_rejection.log`, `/app/config/clients.json`, `/app/docs/legacy_client_contract.md`, and the canonical request samples. Preserve the legacy schema on every attempt, keep internal extension fields out of that schema, and leave modern-client behavior unchanged while retaining milestones 1 through 3.

Repair production sources under `/app/internal/delivery/` only (`client.go`, `payload.go`). The verifier injects its own ephemeral `*_test.go` contract suite at scoring time; do not add local test files under `internal/delivery/` because they can collide with that injected suite.

The verifier captures every initial and retry request for both client generations and checks JSON structure, headers, retry identity, modern-envelope compatibility, and input-payload immutability.
