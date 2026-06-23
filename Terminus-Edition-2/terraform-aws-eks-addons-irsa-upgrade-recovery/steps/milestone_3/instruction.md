# Milestone 3 - Restrict Karpenter capacity placement

Preserve the EKS and add-on recovery while fixing `/app/terraform/karpenter.tf`. Add an `aws_sqs_queue` whose name contains `karpenter-interruption`, and configure Karpenter IRSA with the pinned `terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks` module. Karpenter node classes must discover private infrastructure through `karpenter.sh/discovery`, `subnetSelectorTerms`, and `securityGroupSelectorTerms`; public subnet identifiers or tags are not acceptable.

Define a real Karpenter NodePool named `regulated-on-demand`. Within that NodePool's own manifest, the `karpenter.sh/capacity-type` requirement must allow only `on-demand`; adding `spot` elsewhere in that regulated resource is invalid. Other non-regulated pools may retain mixed capacity. Keep the regulated pool distinct from the default pool and preserve its private node-class selector.

Update `/app/fixtures/scheduling_report.json` without deleting evidence. It must be a JSON object containing a nonempty `regulated_workloads` array. Every array entry must retain its workload `name` and set `capacity_type` to `on-demand` and `nodepool` to `regulated-on-demand`; `addon_pods` remains an array. Success requires the interruption queue, Karpenter IRSA, private selectors, regulated-only placement, and schema-correct scheduling evidence together.
