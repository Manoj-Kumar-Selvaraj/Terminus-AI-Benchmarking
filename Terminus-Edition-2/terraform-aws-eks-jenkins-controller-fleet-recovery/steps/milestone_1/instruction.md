# Milestone 1 - Restore EKS Jenkins fleet topology

The migration left Operations Center unstable and only one controller schedulable. Read `/app/evidence/scheduler_events.log` and `/app/docs/jenkins_fleet_contract.md`, then repair `/app/terraform/eks.tf` and `/app/terraform/jenkins.tf`. Keep `terraform-aws-modules/eks/aws`, use `subnet_ids = var.private_subnet_ids`, set `cluster_endpoint_public_access = false`, and set `cluster_endpoint_private_access = true`.

Inside `eks_managed_node_groups`, restore the dedicated group with the exact key `jenkins_controllers`. Set both `min_size` and `desired_size` to `3`. Its labels must include `workload = "jenkins-controller"` and `dedicated = "jenkins"`, and its dedicated Jenkins taint must use effect `NO_SCHEDULE` or `NoSchedule`. These values must be inside that group, not comments or unrelated blocks.

Restore one `joc` Helm release whose values explicitly set `operationsCenter.enabled: true` and `operationsCenter.replicaCount` to at least 1. Restore exactly `payments-controller`, `risk-controller`, and `platform-controller`. Each controller's own Helm values must include its literal `controllerName:`, target `workload: jenkins-controller`, tolerate the dedicated taint, and define topology spread or pod anti-affinity. Do not replace Terraform with generated verifier output.
