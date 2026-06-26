# Export broker incident timeline

- 09:12 — Emergency signing material `rot-17` is deployed to the profile CI issuer while a partner sandbox already uses the same key identifier.
- 09:18 — A rehearsal assertion with profile claims but partner signing material reaches the export broker. The verifier trace records a successful key-cache lookup.
- 09:27 — After issuer validation is tightened in a limited rehearsal, a support delegation receives an export capability previously cached for an exporter in another request.
- 09:41 — A broker restart during client retries creates two capability serials for one assertion JTI.
- 10:03 — Rotation generation 42 is rehearsed. One stale node acknowledgement is counted, the signer changes early, and rollback reactivates material marked compromised.

No customer export completed. The environment is a deterministic reconstruction of the rehearsal.
