resource "helm_release" "joc" {
  name = "joc"
  namespace = "jenkins"
  chart = "cloudbees-ci"
  values = [<<YAML
controller:
  replicaCount: 0
YAML
  ]
}
resource "helm_release" "payments_controller" {
  name = "payments-controller"
  namespace = "jenkins"
  chart = "cloudbees-controller"
  values = [<<YAML
controller:
  replicaCount: 1
  nodeSelector:
    workload: general
YAML
  ]
}
