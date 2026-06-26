# Milestone 4 — Preserve private audit egress with CIDR exception

Security approved a narrow private-audit endpoint range for emergency reconciliation. Using `/app/evidence/audit_approval.txt` and `/app/evidence/security_review.txt`, update `/app/k8s/networkpolicy.yaml` so TCP `9443` is allowed to CIDR `10.44.0.0/24` with an explicit `except` entry for `10.44.0.200/32`. General Internet egress and the blocked host must remain denied. Preserve prior DNS, ledger, and identity behavior.
