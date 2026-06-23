# Preserve imported state and fail closed on missing NAT capacity

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/vpcsim.py`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident.

## Requirements

- Unchanged imported state must produce zero `replace` plan actions.
- Declare legacy private subnet paths (e.g. `module.vpc.aws_subnet.private`) as `moved` actions to app subnet addresses.
- Fail when an app AZ lacks same-AZ NAT with `missing nat gateway` in the error (include the AZ in the message).
- Preserve `main.tf` labels, `outputs.tf` keys, and vpcsim CLI flags.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
