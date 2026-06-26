# Milestone 3 - Restrict Karpenter capacity placement

Preserve the EKS and add-on recovery while fixing `/app/terraform/karpenter.tf`. Add an `aws_sqs_queue` whose name contains `karpenter-interruption`, and configure Karpenter IRSA with the pinned `terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks` module. Karpenter node classes must discover private infrastructure through `karpenter.sh/discovery`, `subnetSelectorTerms`, and `securityGroupSelectorTerms`; public subnet identifiers or tags are not acceptable.

Define a real Karpenter NodePool named `regulated-on-demand`. Declare it as `resource "kubectl_manifest" "karpenter_regulated_nodepool"` in `/app/terraform/karpenter.tf` (the Kubernetes `metadata.name` is `regulated-on-demand`; the Terraform resource label must be exactly `karpenter_regulated_nodepool`). Embed both the NodePool and its companion `EC2NodeClass` as multi-document YAML (separated by `---`) inside that single resource's `yaml_body` heredoc—the verifier parses only that heredoc, not separate `kubectl_manifest` resources. Within that NodePool's own manifest, the `karpenter.sh/capacity-type` requirement must allow only `on-demand`; adding `spot` elsewhere in that regulated resource is invalid. Other non-regulated pools may retain mixed capacity. Keep the regulated pool distinct from the default pool and preserve its private node-class selector.

Update `/app/fixtures/scheduling_report.json` without deleting evidence. It must match this schema exactly:

```json
{
  "regulated_workloads": [
    {
      "name": "<string>",
      "capacity_type": "on-demand",
      "nodepool": "regulated-on-demand"
    }
  ],
  "addon_pods": [
    {
      "name": "<string>",
      "service_account": "<string>"
    }
  ]
}
```

`regulated_workloads` must be a nonempty array. Keep the existing workload name `settlement-ledger`; do not rename or remove it. Every regulated entry must set `capacity_type` to `on-demand` and `nodepool` to `regulated-on-demand`. `addon_pods` must remain an array.

Success requires the interruption queue, Karpenter IRSA, private selectors, regulated-only placement, and schema-correct scheduling evidence together.
