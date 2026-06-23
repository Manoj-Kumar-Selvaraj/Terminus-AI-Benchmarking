#!/usr/bin/env bash
set -Eeuo pipefail
python3 - <<'__PY__'
from pathlib import Path

root = Path("/app/terraform")
root.joinpath("eks.tf").write_text(
    """module "eks" {
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
)
root.joinpath("jenkins.tf").write_text(
    """resource "helm_release" "joc" {
  name = "joc"
  namespace = "jenkins"
  chart = "cloudbees-ci"
  values = [<<YAML
operationsCenter:
  enabled: true
  replicaCount: 1
controller:
  replicaCount: 1
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
  nodeSelector:
    workload: jenkins-controller
  tolerations:
    - key: dedicated
      value: jenkins
      effect: NoSchedule
  topologySpreadConstraints:
    - topologyKey: kubernetes.io/hostname
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
  nodeSelector:
    workload: jenkins-controller
  tolerations:
    - key: dedicated
      value: jenkins
      effect: NoSchedule
  topologySpreadConstraints:
    - topologyKey: kubernetes.io/hostname
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
  nodeSelector:
    workload: jenkins-controller
  tolerations:
    - key: dedicated
      value: jenkins
      effect: NoSchedule
  topologySpreadConstraints:
    - topologyKey: kubernetes.io/hostname
YAML
  ]
}
"""
)
__PY__
