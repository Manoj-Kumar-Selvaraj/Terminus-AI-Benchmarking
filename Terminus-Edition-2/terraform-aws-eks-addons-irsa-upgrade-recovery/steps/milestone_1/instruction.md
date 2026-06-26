# Milestone 1 - Restore private EKS module and node pools

The upgrade candidate in `/app/terraform/eks.tf` exposes the control plane publicly, uses public subnets, and collapses worker capacity into a default pool. Read `/app/evidence/upgrade_failure.log` and `/app/docs/platform_upgrade_contract.md`, then repair the existing `terraform-aws-modules/eks/aws` module without changing the cluster identity or removing its pinned module version. Set `cluster_endpoint_public_access = false`, `cluster_endpoint_private_access = true`, and `subnet_ids = var.private_subnet_ids`.

Replace the `default` entry inside `eks_managed_node_groups` with actual `system`, `apps`, and `batch` map entries. Each entry must contain `labels = { nodepool = "<entry-name>" }`. Only the `system` entry needs the critical-add-on taint, but that taint must be inside the system group and use key `CriticalAddonsOnly`, value `true`, and effect `NO_SCHEDULE` or `NoSchedule`. Do not satisfy these requirements with comments or unrelated locals: the labels and taint must be structurally nested in their managed-node-group entries.

The verifier checks these exact values in `eks.tf`: `cluster_endpoint_public_access = false`, `cluster_endpoint_private_access = true`, `subnet_ids = var.private_subnet_ids`, three map keys `system`, `apps`, and `batch` each with `nodepool = "<name>"`, the system taint key `CriticalAddonsOnly` with value `true` and effect `NO_SCHEDULE` or `NoSchedule`, and no `default` managed-node-group entry.

Success means the EKS module remains version-pinned, has private-only endpoint and subnet settings, defines all three named managed groups, and contains no `default` managed-node-group entry. Preserve valid variables and unrelated Terraform files for later recovery work.
