#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'__PY__'
from pathlib import Path
import json
root=Path('/app/terraform')
root.joinpath('eks.tf').write_text("""module "eks" {
  source = "terraform-aws-modules/eks/aws"
  version = "20.0.0"
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

root.joinpath('karpenter.tf').write_text("""resource "aws_sqs_queue" "karpenter_interruption" { name = "karpenter-interruption-regulated-platform" }
module "karpenter_irsa" { source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks" version = "5.39.0" role_name = "regulated-karpenter" oidc_providers = { main = { provider_arn = module.eks.oidc_provider_arn namespace_service_accounts = ["karpenter:karpenter"] } } }
resource "kubectl_manifest" "karpenter_default_nodepool" { yaml_body = <<YAML
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
      nodeClassRef:
        name: private-default
---
apiVersion: karpenter.k8s.aws/v1beta1
kind: EC2NodeClass
metadata:
  name: private-default
spec:
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: regulated-platform
        tier: private
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: regulated-platform
YAML
}
resource "kubectl_manifest" "karpenter_regulated_nodepool" { yaml_body = <<YAML
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: regulated-on-demand
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: workload-tier
          operator: In
          values: ["regulated"]
      taints:
        - key: regulated
          value: "true"
          effect: NoSchedule
      nodeClassRef:
        name: regulated-private
---
apiVersion: karpenter.k8s.aws/v1beta1
kind: EC2NodeClass
metadata:
  name: regulated-private
spec:
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: regulated-platform
        tier: private
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: regulated-platform
YAML
}
""")
Path('/app/fixtures/scheduling_report.json').write_text(json.dumps({'regulated_workloads':[{'name':'settlement-ledger','capacity_type':'on-demand','nodepool':'regulated-on-demand'}],'addon_pods':[{'name':'ebs-csi-controller','service_account':'ebs-csi-controller-sa'}]}, indent=2))

root.joinpath('outputs.tf').write_text("""output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "cluster_security_group_id" { value = module.eks.cluster_security_group_id }
output "oidc_provider_arn" { value = module.eks.oidc_provider_arn }
output "private_subnet_ids" { value = var.private_subnet_ids }
output "managed_node_group_names" { value = keys(module.eks.eks_managed_node_groups) }
output "addon_irsa_role_arns" { value = { ebs_csi = module.ebs_csi_irsa.iam_role_arn load_balancer = module.alb_controller_irsa.iam_role_arn karpenter = module.karpenter_irsa.iam_role_arn } }
moved { from = aws_iam_role_policy_attachment.node_addon_admin to = module.ebs_csi_irsa }
""")

Path('/app/fixtures/plan.json').write_text(json.dumps({'resource_changes':[{'address':'module.eks.aws_eks_cluster.this[0]','change':{'actions':['update']}},{'address':'module.eks.aws_security_group.cluster[0]','change':{'actions':['no-op']}},{'address':'module.eks.aws_eks_node_group.this["system"]','change':{'actions':['update']}},{'address':'module.eks.aws_eks_node_group.this["apps"]','change':{'actions':['update']}},{'address':'module.eks.aws_eks_node_group.this["batch"]','change':{'actions':['update']}},{'address':'module.ebs_csi_irsa.aws_iam_role.this[0]','change':{'actions':['update']}}], 'configuration':{'root_module':{'outputs':{k:{} for k in ['cluster_endpoint','cluster_security_group_id','oidc_provider_arn','private_subnet_ids','managed_node_group_names','addon_irsa_role_arns']}}}}, indent=2))
__PY__
