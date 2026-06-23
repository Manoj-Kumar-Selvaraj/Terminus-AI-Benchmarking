# Milestone 3 — Restore identity-token egress and reject broad Internet bypasses

Ledger calls now reach the service but token exchange fails. Add the identity token path described in `/app/docs/egress_contract.md` while preserving least privilege. Do not use `0.0.0.0/0`, empty selectors, or a namespace-wide escape hatch to make the simulator pass.
