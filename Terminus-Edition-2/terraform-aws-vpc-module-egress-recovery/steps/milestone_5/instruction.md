# Preserve imported state and fail closed on missing NAT capacity

You are on the network platform rotation for a failed Terraform AWS VPC module rollout. This is offline: do not call AWS and do not require Terraform. Use `/app/bin/vpcsim`, `/app/docs/module_contract.md`, and `/app/evidence` to diagnose the incident. Repair logic in `/app/infra/modules/vpc/module.go` and rebuild with `go build -o /app/bin/vpcsim /app/cmd/vpcsim`.

## Requirements

- Unchanged imported state must produce zero `replace` plan actions.
- Declare legacy private subnet paths as moved actions to the matching app subnet address for the same CIDR (for example `module.vpc.aws_subnet.private[0]` -> `module.vpc.aws_subnet.app["us-east-1a"]`). Prior state may contain integer-indexed legacy addresses such as `module.vpc.aws_subnet.private[0]` without an `az` field, so match prior subnets by stable CIDR and emit moved objects with `action: "moved"`, `from`, and `to`.
- Moved entries must appear once in the plan evidence used by verifiers. `plan_actions` must contain the `{"action": "moved", "from": "...", "to": "..."}` objects; do not duplicate the same legacy-subnet `from` address in both `moved` and `plan_actions`.
- Fail when an app AZ lacks same-AZ NAT with `missing nat gateway` in the error (include the AZ in the message).
- Preserve `main.tf` labels, `outputs.tf` keys, and vpcsim CLI flags.

Compatibility constraints: keep `/app/infra/modules/vpc`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
