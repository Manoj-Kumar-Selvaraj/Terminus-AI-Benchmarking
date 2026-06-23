# Milestone 2 - Recover add-on IRSA boundaries

Preserve the private EKS cluster and managed-node-group behavior while repairing `/app/terraform/addons.tf` and related EKS module configuration. Declare `vpc-cni`, `coredns`, `kube-proxy`, and `aws-ebs-csi-driver` as core add-ons. Every add-on must have an explicit `addon_version` that is not `latest` and must set `resolve_conflicts_on_update = "PRESERVE"`; connect the resulting add-on map to the EKS module.

Create narrowly scoped EBS CSI and AWS Load Balancer Controller roles with `terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks` and a pinned module version. Bind EBS CSI to `kube-system:ebs-csi-controller-sa` and the load balancer controller to `kube-system:aws-load-balancer-controller`. Their Kubernetes or Helm service-account configuration must set `eks.amazonaws.com/role-arn` to the corresponding IRSA role rather than an empty value.

Remove the legacy `aws_iam_role_policy_attachment.node_addon_admin` resource and all `AdministratorAccess` references. Do not introduce IAM statements with wildcard `Action = "*"` or `Resource = "*"`. Success means all four add-ons are pinned with update-conflict preservation, both named controllers use their own annotated service accounts, and the broad node-role path is absent while milestone 1 remains intact.
