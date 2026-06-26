After lease fencing was repaired, HSM audit still showed two signatures for one authorization when the process crashed after the external side effect but before local commit. Review `/app/evidence/hsm_audit_excerpt.log`, `/app/docs/signing_recovery_contract.md`, and the existing request journal.

Make signing and recovery use stable durable operation identity while preserving milestone 1. The request must be prepared before the HSM call; retries and recovery must reuse that preparation, consult the HSM audit, return an existing committed signature, and reject request-ID reuse with different payload. Concurrent callers for one request may create only one HSM operation, while independent pending requests must all recover.

The verifier injects crashes before and after HSM execution, restarts the process, repeats recovery, races same-request callers, exercises conflicting payloads and stale tokens, and counts actual HSM audit rows rather than trusting summaries.
