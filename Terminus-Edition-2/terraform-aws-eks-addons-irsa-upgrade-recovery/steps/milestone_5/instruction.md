# Milestone 5 - Pass the non-destructive plan and drift guard

Finish the recovery without replacing protected infrastructure. `/app/fixtures/plan.json` is offline Terraform plan evidence. It must match this structure:

```json
{
  "resource_changes": [
    {
      "address": "<terraform-address>",
      "change": {
        "actions": ["no-op" | "read" | "update"]
      }
    }
  ],
  "configuration": {
    "root_module": {
      "outputs": {
        "cluster_endpoint": {},
        "cluster_security_group_id": {},
        "oidc_provider_arn": {},
        "private_subnet_ids": {},
        "managed_node_group_names": {},
        "addon_irsa_role_arns": {}
      }
    }
  }
}
```

Retain one `resource_changes` entry for each protected address: `module.eks.aws_eks_cluster.this[0]`, `module.eks.aws_security_group.cluster[0]`, and the `system`, `apps`, and `batch` addresses under `module.eks.aws_eks_node_group.this`. Each protected entry may use only `no-op`, `read`, or `update` actions; it must not contain `delete` or a replacement sequence.

The plan's `configuration.root_module.outputs` object must contain all six legacy output names listed above. Neither Terraform nor the plan may contain `AdministratorAccess`; remove the `aws_iam_role_policy_attachment.node_addon_admin` resource from Terraform and do not include any plan action that creates an address containing that name. Keep the `moved` block in `/app/terraform/outputs.tf` that records `from = aws_iam_role_policy_attachment.node_addon_admin` to `module.ebs_csi_irsa` — removing that migration metadata is invalid even after the legacy attachment resource is deleted. Keep the private endpoint, private subnets, split groups, pinned add-ons, IRSA, regulated Karpenter placement, outputs, and moved metadata from earlier work.

Run `/app/scripts/plan_guard`. It must exit zero and emit JSON containing `{"ok": true}`. Editing the plan alone is insufficient: the Terraform files must independently express the recovered state, and deleting protected resource evidence from `resource_changes` is a guard failure.
