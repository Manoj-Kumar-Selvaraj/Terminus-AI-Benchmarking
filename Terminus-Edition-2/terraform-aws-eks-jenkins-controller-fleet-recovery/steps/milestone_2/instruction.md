# Milestone 2 - Recover IRSA and persistent Jenkins home

Preserve the private topology and four Helm releases while repairing `/app/terraform/service_accounts.tf`, `/app/terraform/storage.tf`, and the related values in `/app/terraform/jenkins.tf`. Use the pinned `terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks` module. Define service-account resources named `joc`, `payments-controller`, `risk-controller`, and `platform-controller`; each resource's own metadata must carry `eks.amazonaws.com/role-arn`. The matching Helm release must bind that same identity through `serviceAccount.name` or `serviceAccountName`.

Provision an `aws_efs_file_system` with `encrypted = true` and an EFS CSI storage class using `efs.csi.aws.com`. That storage-class resource must set `reclaim_policy = "Retain"`. Define and mount four persistent claims: `joc-home`, `payments-controller-home`, `risk-controller-home`, and `platform-controller-home`. Each claim must appear in storage configuration and as the corresponding release's `existingClaim`.

Remove static `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` data and any AWS-key Kubernetes secret. Jenkins home must not use `emptyDir` or `hostPath`. Success requires all four scoped IRSA identities and all four retained EFS homes while preserving milestone 1 scheduling.
