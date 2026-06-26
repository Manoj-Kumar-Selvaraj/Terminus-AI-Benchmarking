# Payments API EC2 rollout incident

All times are UTC on 2026-06-18.

- 09:02 — Release `build-20260618.4` was approved with immutable AMI and bootstrap provenance.
- 09:07 — The production module rendered a launch template from the mutable `latest` catalog entry instead of the approved manifest.
- 09:11 — Replacement instances appeared in public subnets with public IPv4 addresses and an SSH rule open to the internet.
- 09:14 — The refresh controller terminated old capacity before the pilot instance passed health checks. Healthy capacity fell below the payments SLO.
- 09:18 — Operators stopped the rollout. One control-plane response was lost after a pilot commit, leaving the refresh state ambiguous.
- 09:23 — A retry created duplicate instance identities and moved one retained data volume twice.
- 09:31 — Rollback restored service, but storage inventory showed attachment-generation drift and one volume linked to the wrong logical slot.
- 10:05 — Security review found IMDSv1 allowed and an administrator-style instance policy.
- 10:22 — The next plan proposed destructive replacement for instances imported from the legacy module and attempted to "repair" manual drift rather than reporting it.

Recover the existing module without live AWS access. The simulator models the control-plane contracts, restart behavior, imported state, and failure evidence from this incident.
