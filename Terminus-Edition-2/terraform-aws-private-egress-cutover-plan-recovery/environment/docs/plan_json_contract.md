# Plan JSON contract

Verifiers inspect Terraform JSON plan output from isolated fixture workspaces. Resource addresses, actions, and dependency shapes must be derived from module inputs rather than hardcoded fixture snapshots.

Plans must not introduce public-facing PrivateLink policies, wildcard endpoint grants, or mixed old/new egress semantics across app and data route tables.
