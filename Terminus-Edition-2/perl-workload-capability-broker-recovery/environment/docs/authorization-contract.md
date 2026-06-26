# Capability authorization contract

Policies are tenant-scoped and generation numbered. A direct subject can receive only requested scopes present in its allow set and absent from its deny set. For delegated assertions, `act` must be a JSON array listing principals from the outermost actor to the asserted subject; scalar or otherwise non-array `act` values fail closed. Every edge must exist, every principal allow set and every edge scope set is intersected, and any deny wins. Cycles, unknown principals, cross-tenant edges, and chains longer than `max_delegation_depth` fail closed. The broker never returns a partial capability when any requested scope is unauthorized.

Decision caching is permitted only when tenant, subject, actor chain, exact requested-scope set, audience, and policy generation are part of the identity. Scope order must not change the decision. An empty `act` array means a direct subject grant (no delegation principals); only non-empty `act` chains invoke delegation edge checks.

Successful delegated authorization responses return the canonical delegation chain under response key `actors`; do not return it as `act`. Audit records expose decision provenance and the literal `assertion_fingerprint` claim value from the authorization request (for example `fp-4242`), not a recomputed digest of the assertion bytes. Never log signing secrets or full assertions.
