# Milestone 4 — Preserve private audit egress with CIDR exception

Security approved a narrow private-audit endpoint range for emergency reconciliation. Update `/app/k8s/networkpolicy.yaml` so TCP 9443 to the private audit range is allowed while the blocked host exception and general Internet egress remain denied. Preserve prior DNS, ledger, and identity behavior.
