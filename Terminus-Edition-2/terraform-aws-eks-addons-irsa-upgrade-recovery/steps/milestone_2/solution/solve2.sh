#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'__PY__'
from pathlib import Path
import json
root=Path('/app/terraform')
root.joinpath('eks.tf').write_text("""module "eks" {
  source = "terraform-aws-modules/eks/aws"
  version = "20.31.6"
  cluster_name = var.cluster_name
  vpc_id = var.vpc_id
  subnet_ids = var.private_subnet_ids
  cluster_endpoint_public_access = false
  cluster_endpoint_private_access = true
  cluster_addons = local.cluster_addons
  eks_managed_node_groups = {
    system = { min_size = 2 max_size = 4 desired_size = 2 labels = { nodepool = "system" } taints = { critical = { key = "CriticalAddonsOnly" value = "true" effect = "NO_SCHEDULE" } } }
    apps = { min_size = 2 max_size = 6 desired_size = 3 labels = { nodepool = "apps" } }
    batch = { min_size = 0 max_size = 10 desired_size = 1 labels = { nodepool = "batch" } }
  }
}
""")
root.joinpath('addons.tf').write_text("""module "ebs_csi_irsa" { source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks" version = "5.39.0" role_name = "regulated-ebs-csi" oidc_providers = { main = { provider_arn = module.eks.oidc_provider_arn namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"] } } }
module "alb_controller_irsa" { source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks" version = "5.39.0" role_name = "regulated-alb-controller" oidc_providers = { main = { provider_arn = module.eks.oidc_provider_arn namespace_service_accounts = ["kube-system:aws-load-balancer-controller"] } } }
locals { cluster_addons = { vpc-cni = { addon_version = "v1.18.2-eksbuild.1" resolve_conflicts_on_update = "PRESERVE" } coredns = { addon_version = "v1.11.1-eksbuild.9" resolve_conflicts_on_update = "PRESERVE" } kube-proxy = { addon_version = "v1.30.0-eksbuild.3" resolve_conflicts_on_update = "PRESERVE" } aws-ebs-csi-driver = { addon_version = "v1.31.0-eksbuild.1" service_account_role_arn = module.ebs_csi_irsa.iam_role_arn resolve_conflicts_on_update = "PRESERVE" } } }
resource "helm_release" "aws_load_balancer_controller" { name = "aws-load-balancer-controller" namespace = "kube-system" set { name = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn" value = module.alb_controller_irsa.iam_role_arn } }
resource "kubernetes_service_account" "ebs_csi_controller" { metadata { name = "ebs-csi-controller-sa" namespace = "kube-system" annotations = { "eks.amazonaws.com/role-arn" = module.ebs_csi_irsa.iam_role_arn } } }
resource "kubernetes_service_account" "aws_load_balancer_controller" { metadata { name = "aws-load-balancer-controller" namespace = "kube-system" annotations = { "eks.amazonaws.com/role-arn" = module.alb_controller_irsa.iam_role_arn } } }

""")
__PY__
