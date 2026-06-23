# Milestone 5 - Pass the non-destructive plan and drift guard

Finish the recovery without replacing protected infrastructure. `/app/fixtures/plan.json` is offline Terraform plan evidence with top-level `resource_changes` and `configuration.root_module.outputs`. Retain one resource-change entry for each protected address: `module.eks.aws_eks_cluster.this[0]`, `module.eks.aws_security_group.cluster[0]`, and the `system`, `apps`, and `batch` addresses under `module.eks.aws_eks_node_group.this`. Each protected entry may use only `no-op`, `read`, or `update` actions; it must not contain `delete` or a replacement sequence.

The plan's root output object must contain the six legacy names documented in `/app/docs/platform_upgrade_contract.md`. Neither Terraform nor the plan may contain `AdministratorAccess`; remove `node_addon_admin` from Terraform and do not include any plan action that creates an address containing that name. Keep the private endpoint, private subnets, split groups, pinned add-ons, IRSA, regulated Karpenter placement, outputs, and moved metadata from earlier work.

Run `/app/scripts/plan_guard.py`. It must exit zero and emit JSON containing `{"ok": true}`. Editing the plan alone is insufficient: the Terraform files must independently express the recovered state, and deleting protected resource evidence from `resource_changes` is a guard failure.
