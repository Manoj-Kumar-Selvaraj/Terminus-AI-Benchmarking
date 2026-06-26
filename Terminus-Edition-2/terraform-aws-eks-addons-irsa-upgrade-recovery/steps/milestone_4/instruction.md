# Milestone 4 - Preserve upgrade compatibility outputs

Preserve the private cluster, IRSA, and Karpenter behavior while repairing `/app/terraform/outputs.tf`. Downstream consumers require six legacy output blocks named exactly `cluster_endpoint`, `cluster_security_group_id`, `oidc_provider_arn`, `private_subnet_ids`, `managed_node_group_names`, and `addon_irsa_role_arns`. Each block must contain a real `value` expression rooted at `module.` or `var.`; empty strings, placeholder literals, comments, and a replacement-only `cluster_endpoint_url` output do not satisfy the contract. The add-on role output must map `ebs_csi`, `load_balancer`, and `karpenter` to recovered module role ARN expressions.

Retain exact module version pins in the Terraform configuration. Record the legacy attachment refactor with one syntactically balanced `moved` block whose two addresses are `from = aws_iam_role_policy_attachment.node_addon_admin` and `to = module.ebs_csi_irsa`. Both addresses must occur in the same block; unrelated or partial moved metadata is invalid.

The verifier checks all six output names, real `value` expressions, absence of `cluster_endpoint_url`, a pinned module `version`, and the paired `moved` block addresses above.

Success means all six named output blocks are structurally complete, their expressions reference the recovered Terraform objects, the obsolete URL-only name is absent, and migration metadata preserves the specified address transition. Keep braces balanced across every `.tf` file and do not reintroduce broad node administration while restoring compatibility.
