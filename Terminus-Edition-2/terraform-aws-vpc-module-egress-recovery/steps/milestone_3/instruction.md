# Make AZ expansion and CIDR validation safe

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/vpcsim.py`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident.

## Requirements

- Reject overlapping subnet CIDRs with errors containing `overlaps`.
- Reject subnets outside the VPC CIDR with errors containing `outside vpc_cidr`.
- When appending a new AZ, preserve existing subnet IDs for unchanged CIDRs.
- AZ expansion must not emit destructive `replace` actions in `plan_actions`.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
