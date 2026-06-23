# Make instance refresh safe under pilot failure

You are recovering a Terraform AWS EC2 module rollout for the payments API fleet. This is offline: do not call AWS and do not require Terraform. Use `/app/tools/ec2sim.py`, `/app/docs/module_contract.md`, and `/app/evidence`.

Implement pilot-then-batch behavior that preserves old capacity on failed candidate health and is idempotent.

## Success criteria

- Preserve milestones 1–2 placement and ingress behavior.
- Passing refresh uses the pilot-then-batch `strategy` from `/app/docs/module_contract.md` with `min_healthy_percentage >= 90` and `min_healthy_instances >= 5`.
- Failed `candidate_health` rolls back with `status: rolled_back`, event `kept_previous_capacity`, and prior instance IDs unchanged.
- Re-running `plan` with `--prior-state` does not duplicate instance IDs.

Compatibility constraints: keep `/app/infra/modules/ec2`, all labels in `main.tf`, all outputs in `outputs.tf`, and CLI flags `plan`, `apply`, `validate`, `--config`, `--prior-state`, `--out`, `--state`. Do not hardcode sample JSON or edit verifier fixtures.
