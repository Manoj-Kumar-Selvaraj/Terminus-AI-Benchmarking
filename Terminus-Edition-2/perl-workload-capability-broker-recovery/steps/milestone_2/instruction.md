Assertion verification is now trustworthy, but the staged export path still grants export scope to requests that should be denied. The outcome changes with request order, tenant traffic, and a recent policy generation, and a support delegation has inherited an exporter decision. Investigate `/app/evidence/policy-cache-snapshot.json`, `/app/docs/authorization-contract.md`, and the existing Perl policy path.

Restore tenant-scoped direct and delegated authorization without weakening assertion checks.

## Success criteria

1. Direct subjects receive only the **exact requested scopes** present in their allow set and absent from deny.
2. Subject deny overrides allow (for example `svc-support` must not receive `profile:export` even when a parent allow exists).
3. Tenant decisions cannot bleed through cache: `acme` and `globex` remain isolated.
4. Documented delegation chains are accepted and returned with the full actor list under response key `actors`; invalid edges, cycles, excessive depth, unknown principals, and non-array `act` values fail closed. An empty `act` array is a direct grant, not a delegation rejection.
5. Policy generation changes invalidate stale cached decisions when `/app/runtime/config/policy.json` generation advances.
6. Requested scope ordering must not change semantics: `profile:export,profile:read` and `profile:read,profile:export` share one `cache_key` and canonical scope output.
7. Audit records include the literal `assertion_fingerprint` claim value from the authorization request and `policy_generation` provenance but never signing secrets or full assertions.

Do not modify `/opt/task-tools`.
