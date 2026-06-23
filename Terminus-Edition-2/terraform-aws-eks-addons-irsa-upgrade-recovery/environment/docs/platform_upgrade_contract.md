# EKS platform upgrade contract

Use `terraform-aws-modules/eks/aws`. Keep the API endpoint private (`cluster_endpoint_public_access = false`, `cluster_endpoint_private_access = true`) and `subnet_ids` pointed at `var.private_subnet_ids`. Use managed node groups named `system`, `apps`, and `batch` inside `eks_managed_node_groups` (remove any `default` pool).

## Milestone 1 — Node groups and system taint

Each node group must include `labels = { nodepool = "<name>" }` where `<name>` is `system`, `apps`, or `batch`.

The `system` group must taint nodes with:

- key: `CriticalAddonsOnly`
- value: `true`
- effect: `NO_SCHEDULE` (or `NoSchedule`)

## Milestone 2 — Add-ons and IRSA

Core EKS add-ons (`vpc-cni`, `coredns`, `kube-proxy`, `aws-ebs-csi-driver`) must use pinned `addon_version` values (no `latest`) and `resolve_conflicts_on_update = "PRESERVE"`.

EBS CSI and AWS Load Balancer Controller must use IRSA via `terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks` with service accounts:

- `kube-system:ebs-csi-controller-sa`
- `kube-system:aws-load-balancer-controller`

Annotate pods/service accounts with `eks.amazonaws.com/role-arn`. Do not attach `AdministratorAccess`, `node_addon_admin`, or wildcard IAM policies (`Action = "*"`, `Resource = "*"`).

## Milestone 3 — Karpenter and scheduling report

Karpenter must include:

- an `aws_sqs_queue` for interruption handling (name contains `karpenter-interruption`)
- IRSA for Karpenter via `terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks`
- private selectors (`karpenter.sh/discovery`, `subnetSelectorTerms`, `securityGroupSelectorTerms`; no public subnet tags)
- a `regulated-on-demand` NodePool that allows only `on-demand` capacity (no `spot`)

### scheduling_report.json schema

`/app/fixtures/scheduling_report.json` must keep at least one regulated workload entry:

```json
{
  "regulated_workloads": [
    {
      "name": "<workload-name>",
      "capacity_type": "on-demand",
      "nodepool": "regulated-on-demand"
    }
  ],
  "addon_pods": [ ... ]
}
```

Do not delete or empty `regulated_workloads`.

## Milestone 4 — Legacy outputs and moved blocks

`outputs.tf` must expose these legacy output names with real module/var expressions (not empty strings):

- `cluster_endpoint`
- `cluster_security_group_id`
- `oidc_provider_arn`
- `private_subnet_ids`
- `managed_node_group_names`
- `addon_irsa_role_arns`

Do not rename to `cluster_endpoint_url` only.

Include a `moved` block pairing:

- `from = aws_iam_role_policy_attachment.node_addon_admin`
- `to = module.ebs_csi_irsa`

Keep Terraform module `version` pins.

## Milestone 5 — plan.json schema

`/app/fixtures/plan.json` must pass `/app/scripts/plan_guard.py`. Protected resources must not be deleted or replaced:

- `module.eks.aws_eks_cluster.this[0]`
- `module.eks.aws_security_group.cluster[0]`
- `module.eks.aws_eks_node_group.this["system"]`
- `module.eks.aws_eks_node_group.this["apps"]`
- `module.eks.aws_eks_node_group.this["batch"]`

Root module outputs in `configuration.root_module.outputs` must include:

- `cluster_endpoint`
- `cluster_security_group_id`
- `oidc_provider_arn`
- `private_subnet_ids`
- `managed_node_group_names`
- `addon_irsa_role_arns`

Broad node admin attachments (`node_addon_admin`) must be removed from Terraform and must not appear as `create` actions in the plan.
