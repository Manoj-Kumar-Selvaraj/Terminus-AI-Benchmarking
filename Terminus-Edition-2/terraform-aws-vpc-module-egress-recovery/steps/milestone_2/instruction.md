# Recover gateway endpoint route-table ownership

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/bin/vpcsim`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident. Repair logic in `/app/infra/modules/vpc/module.go` and rebuild with `go build -o /app/bin/vpcsim /app/cmd/vpcsim`.

## Requirements

- Attach S3 and DynamoDB gateway endpoints only to app route tables (not public or data tables).
- Fail closed on unsupported gateway endpoint services with `unsupported` in the validation error.
- Preserve endpoint policy account provenance and tags. The policy must remain a nested IAM document with `policy.Statement[0].Condition.StringEquals["aws:PrincipalAccount"] == "111122223333"`, and endpoint tags must include `ManagedBy: terraform-aws-vpc-module`.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
