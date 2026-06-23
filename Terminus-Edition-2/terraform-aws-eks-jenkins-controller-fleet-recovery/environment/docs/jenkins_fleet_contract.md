# Jenkins EKS fleet contract

Run one Operations Center pod and exactly three controller pods: payments-controller, risk-controller, and platform-controller. Controller pods must schedule on a dedicated Jenkins controller node group. JENKINS_HOME must survive rescheduling. Cloud credentials must use IRSA annotations, not static AWS keys. Jobs are created from code and exercised by the offline simulator. Payments jobs run only on payments-controller, risk jobs only on risk-controller, and platform jobs only on platform-controller. Required plugins are pinned and sourced from an internal mirror. Public update center and script console remain disabled.

The managed node-group key is `jenkins_controllers`; it has minimum and desired size 3, labels `workload = "jenkins-controller"` and `dedicated = "jenkins"`, plus a Jenkins dedicated `NoSchedule` taint. Controller Helm values expose their literal `controllerName`. The fleet contains at least six production jobs, with at least two assigned to each controller.

## Internal plugin source

`plugin-catalog.yaml` must set `pluginSource: internal-mirror` and must not reference `updates.jenkins.io`.

## Approved plugin IDs

The fleet approves exactly these plugin IDs:

- configuration-as-code
- kubernetes
- workflow-aggregator
- job-dsl
- git
- credentials
- matrix-auth
- cloudbees-casc-client

## Legacy Terraform outputs (must remain)

Downstream modules depend on these output names in `outputs.tf` and the upgrade plan fixture:

- joc_hostname
- joc_url
- controller_names
- jenkins_namespace
- irsa_role_arns
