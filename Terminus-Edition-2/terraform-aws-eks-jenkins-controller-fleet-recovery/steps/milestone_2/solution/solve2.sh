#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'__PY__'
from pathlib import Path

root = Path("/app/terraform")

EKS_TF = """module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.11.1"
  cluster_name = var.cluster_name
  vpc_id = var.vpc_id
  subnet_ids = var.private_subnet_ids
  cluster_endpoint_public_access  = false
  cluster_endpoint_private_access = true
  eks_managed_node_groups = {
    jenkins_controllers = { min_size = 3 max_size = 6 desired_size = 3 labels = { workload = "jenkins-controller" dedicated = "jenkins" } taints = { dedicated = { key = "dedicated" value = "jenkins" effect = "NO_SCHEDULE" } } }
    system = { min_size = 2 max_size = 3 desired_size = 2 labels = { workload = "system" } }
  }
}
"""

JENKINS_TF = """resource "helm_release" "joc" {
  name = "joc"
  namespace = "jenkins"
  chart = "cloudbees-ci"
  values = [<<YAML
operationsCenter:
  enabled: true
  replicaCount: 1
controller:
  replicaCount: 1
  persistence:
    existingClaim: joc-home
serviceAccount:
  name: joc
YAML
  ]
}
resource "helm_release" "payments_controller" {
  name = "payments-controller"
  namespace = "jenkins"
  chart = "cloudbees-controller"
  values = [<<YAML
controllerName: payments-controller
controller:
  replicaCount: 1
  persistence:
    existingClaim: payments-controller-home
  nodeSelector:
    workload: jenkins-controller
  tolerations:
    - key: dedicated
      value: jenkins
      effect: NoSchedule
  topologySpreadConstraints:
    - topologyKey: kubernetes.io/hostname
serviceAccount:
  name: payments-controller
YAML
  ]
}
resource "helm_release" "risk_controller" {
  name = "risk-controller"
  namespace = "jenkins"
  chart = "cloudbees-controller"
  values = [<<YAML
controllerName: risk-controller
controller:
  replicaCount: 1
  persistence:
    existingClaim: risk-controller-home
  nodeSelector:
    workload: jenkins-controller
  tolerations:
    - key: dedicated
      value: jenkins
      effect: NoSchedule
  topologySpreadConstraints:
    - topologyKey: kubernetes.io/hostname
serviceAccount:
  name: risk-controller
YAML
  ]
}
resource "helm_release" "platform_controller" {
  name = "platform-controller"
  namespace = "jenkins"
  chart = "cloudbees-controller"
  values = [<<YAML
controllerName: platform-controller
controller:
  replicaCount: 1
  persistence:
    existingClaim: platform-controller-home
  nodeSelector:
    workload: jenkins-controller
  tolerations:
    - key: dedicated
      value: jenkins
      effect: NoSchedule
  topologySpreadConstraints:
    - topologyKey: kubernetes.io/hostname
serviceAccount:
  name: platform-controller
YAML
  ]
}
"""

SERVICE_ACCOUNTS_TF = """module "jenkins_irsa" {
  source = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.39.0"
  role_name = "jenkins-fleet-irsa"
  oidc_providers = {
    main = {
      provider_arn = module.eks.oidc_provider_arn
      namespace_service_accounts = [
        "jenkins:joc",
        "jenkins:payments-controller",
        "jenkins:risk-controller",
        "jenkins:platform-controller",
      ]
    }
  }
}
resource "kubernetes_service_account" "joc" {
  metadata {
    name = "joc"
    namespace = "jenkins"
    annotations = { "eks.amazonaws.com/role-arn" = module.jenkins_irsa.iam_role_arn }
  }
}
resource "kubernetes_service_account" "payments_controller" {
  metadata {
    name = "payments-controller"
    namespace = "jenkins"
    annotations = { "eks.amazonaws.com/role-arn" = module.jenkins_irsa.iam_role_arn }
  }
}
resource "kubernetes_service_account" "risk_controller" {
  metadata {
    name = "risk-controller"
    namespace = "jenkins"
    annotations = { "eks.amazonaws.com/role-arn" = module.jenkins_irsa.iam_role_arn }
  }
}
resource "kubernetes_service_account" "platform_controller" {
  metadata {
    name = "platform-controller"
    namespace = "jenkins"
    annotations = { "eks.amazonaws.com/role-arn" = module.jenkins_irsa.iam_role_arn }
  }
}
"""

STORAGE_TF = """resource "aws_efs_file_system" "jenkins_home" {
  encrypted = true
  tags = { Name = "jenkins-home" }
}
resource "kubernetes_storage_class" "jenkins_efs" {
  metadata { name = "jenkins-efs" }
  storage_provisioner = "efs.csi.aws.com"
  reclaim_policy = "Retain"
  parameters = {
    provisioningMode = "efs-ap"
    fileSystemId = aws_efs_file_system.jenkins_home.id
    directoryPerms = "750"
  }
}
resource "kubernetes_persistent_volume_claim" "joc_home" {
  metadata { name = "joc-home" namespace = "jenkins" }
  spec { storage_class_name = kubernetes_storage_class.jenkins_efs.metadata[0].name }
}
resource "kubernetes_persistent_volume_claim" "payments_controller_home" {
  metadata { name = "payments-controller-home" namespace = "jenkins" }
  spec { storage_class_name = kubernetes_storage_class.jenkins_efs.metadata[0].name }
}
resource "kubernetes_persistent_volume_claim" "risk_controller_home" {
  metadata { name = "risk-controller-home" namespace = "jenkins" }
  spec { storage_class_name = kubernetes_storage_class.jenkins_efs.metadata[0].name }
}
resource "kubernetes_persistent_volume_claim" "platform_controller_home" {
  metadata { name = "platform-controller-home" namespace = "jenkins" }
  spec { storage_class_name = kubernetes_storage_class.jenkins_efs.metadata[0].name }
}
"""

root.joinpath("eks.tf").write_text(EKS_TF)
root.joinpath("jenkins.tf").write_text(JENKINS_TF)
root.joinpath("service_accounts.tf").write_text(SERVICE_ACCOUNTS_TF)
root.joinpath("storage.tf").write_text(STORAGE_TF)
__PY__
