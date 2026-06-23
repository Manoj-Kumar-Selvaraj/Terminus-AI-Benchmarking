# Milestone 2 — Allow ledger API without broadening namespace access

After DNS is restored, ledger posting still times out. Update `/app/k8s/networkpolicy.yaml` using `/app/evidence/ledger_timeout_trace.log` and `/app/docs/egress_contract.md`. The adapter must reach only the ledger API pods on TCP 443 while preserving DNS behavior and existing Deployment labels.
