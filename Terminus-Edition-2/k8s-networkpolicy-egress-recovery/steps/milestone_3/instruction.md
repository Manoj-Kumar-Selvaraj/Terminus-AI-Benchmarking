# Milestone 3 — Restore identity-token egress and reject broad Internet bypasses

Ledger calls now reach the service but token exchange fails. Add the identity token path from `/app/docs/egress_contract.md`: namespace label `name: identity`, pod label `app: token-service`, TCP port `8443`. Preserve least privilege and do not use `0.0.0.0/0`, empty selectors, or a namespace-wide escape hatch.
