The customer-profile export broker is accepting a rehearsal assertion that claims the production issuer and tenant even though the signing material came from a partner sandbox. Other traces show prefix-like audiences passing, while some legitimate rotation assertions fail unpredictably. Use `/app/evidence/verification-trace.log`, `/app/evidence/incident-timeline.md`, and `/app/docs/assertion-contract.md` to restore trustworthy assertion verification.

Keep `/app/bin/brokerctl`, the compact `SWA1` token format, issuer/key identities, and the protected runtime under `/opt/task-tools` compatible. Repair `/app/lib/Broker/Assertion.pm` (and related Perl modules) so verification is read-only, exact, time-aware, and issuer scoped.

## Success criteria

1. Legitimate `profile-ci` assertions with audience `profile-export` verify successfully and preserve the claim issuer.
2. A partner signing key cannot impersonate production: colliding KIDs for different issuers must fail signature or trust checks.
3. Audience membership is **exact set membership** — `profile-export-admin` must not satisfy a request for `profile-export`.
4. Tenant is bound to issuer: a `partner-ci` assertion cannot use tenant `acme` unless contract rules allow it (including `source_epoch` minimum checks).
5. Only `HS256` is accepted; unsupported algorithms such as `HS512` are rejected.
6. Retired issuer keys (for example `legacy-1`) are not accepted.
7. Configured clock skew applies symmetrically to `nbf`, `iat`, and `exp`; boundary cases inside skew pass and outside skew fail.
8. Payload tampering invalidates the signature without rewriting claim bytes before verification.
9. Repeated verification of the same assertion is deterministic and does not mutate broker keys, replay state, or journals.

Do not disable signatures, expiry, tenant checks, or rotation overlap behavior. Do not modify `/opt/task-tools`.
