# Restore same-AZ app egress and isolated data routes

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/vpcsim.py`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident.

## Requirements

- Restore app route tables so each app subnet's `0.0.0.0/0` route targets the NAT gateway in the same AZ.
- Remove all default internet routes from isolated data route tables.
- Preserve output keys: `vpc_id`, `public_subnet_ids`, `private_app_subnet_ids`, `isolated_data_subnet_ids`, `private_app_route_table_ids`, `isolated_data_route_table_ids`.
- Keep subnet tags `Name` and `Tier` on every subnet.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
