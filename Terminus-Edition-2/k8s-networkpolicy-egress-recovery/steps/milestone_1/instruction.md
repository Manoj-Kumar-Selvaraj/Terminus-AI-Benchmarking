# Milestone 1 — Recover DNS egress under default-deny

The payment adapter pods are running but cannot resolve service names after a default-deny rollout. Use `/app/evidence/dns_failure_events.log` and `/app/docs/networkpolicy_selector_notes.md` to update `/app/k8s/networkpolicy.yaml`. The policy must select the existing payment adapter pods and allow kube-dns over both UDP and TCP port 53 without opening unrelated egress.
