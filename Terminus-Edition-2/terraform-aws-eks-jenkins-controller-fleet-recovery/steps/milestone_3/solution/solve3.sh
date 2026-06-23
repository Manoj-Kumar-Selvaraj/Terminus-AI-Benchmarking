#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'__PY__'
import json
import re
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

catalog = """pluginSource: internal-mirror
plugins:
  - id: configuration-as-code
    version: "1850.v3b_ca_9b_914b_4c"
  - id: kubernetes
    version: "4246.v5a_12b_1fe120e"
  - id: workflow-aggregator
    version: "596.v8c21c963d92d"
  - id: job-dsl
    version: "1.87"
  - id: git
    version: "5.2.2"
  - id: credentials
    version: "1337.v60b_d7b_c7b_c9f"
  - id: matrix-auth
    version: "3.2.2"
  - id: cloudbees-casc-client
    version: "2.277.0.3"
"""
root.joinpath("plugin-catalog.yaml").write_text(catalog)
root.joinpath("jcasc.yaml").write_text(
    """jenkins:
  systemMessage: "Jenkins fleet managed by Terraform and JCasC"
  securityRealm:
    local:
      allowsSignup: false
  authorizationStrategy:
    matrix:
      permissions:
        - "Overall/Read:authenticated"
        - "Job/Build:jenkins-operators"
"""
)
jobs = {
    "controllers": {
        "payments-controller": {
            "seed_job": "payments-seed",
            "jobs": ["payments-release", "payments-smoke"],
        },
        "risk-controller": {
            "seed_job": "risk-seed",
            "jobs": ["risk-nightly-scan", "risk-policy-verify"],
        },
        "platform-controller": {
            "seed_job": "platform-seed",
            "jobs": ["platform-smoke", "platform-plugin-audit"],
        },
    },
    "jobs": {
        "payments-release": {
            "controller": "payments-controller",
            "folder": "payments",
            "required_plugins": ["workflow-aggregator", "git", "credentials"],
        },
        "payments-smoke": {
            "controller": "payments-controller",
            "folder": "payments",
            "required_plugins": ["job-dsl", "git"],
        },
        "risk-nightly-scan": {
            "controller": "risk-controller",
            "folder": "risk",
            "required_plugins": ["workflow-aggregator", "matrix-auth"],
        },
        "risk-policy-verify": {
            "controller": "risk-controller",
            "folder": "risk",
            "required_plugins": ["job-dsl", "credentials"],
        },
        "platform-smoke": {
            "controller": "platform-controller",
            "folder": "platform",
            "required_plugins": ["workflow-aggregator", "kubernetes"],
        },
        "platform-plugin-audit": {
            "controller": "platform-controller",
            "folder": "platform",
            "required_plugins": ["job-dsl", "configuration-as-code"],
        },
    },
}
root.joinpath("jenkins_jobs.json").write_text(json.dumps(jobs, indent=2))
__PY__
