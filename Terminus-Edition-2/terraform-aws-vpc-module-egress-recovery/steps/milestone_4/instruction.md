# Audit and resolver policy reconciliation

Preserve Milestones 1 through 3. Extend recovery to reconcile audit-grade flow logs and resolver security while keeping the recovered routing, endpoint, and imported-state behavior intact.

Requirements:

- Flow logs must cover every recovered subnet and expose the covered subnet IDs under `flow_log.subnet_ids`.
- When the configured flow-log destination account matches the VPC account, preserve the existing flow-log ID and audit metadata from `evidence/audit_inventory.json`.
- Flow-log IAM policy must be a scoped flat object with `Action` and `Resource`, not a wildcard policy and not `logs:*`.
- The flow-log IAM policy `Resource` must be a CloudWatch Logs ARN for the configured account and log group, must include `log-group:`, must end with `:*`, and must not be an account-wide wildcard resource.
- The flow-log IAM policy `Action` list must include at least `logs:CreateLogStream` and `logs:PutLogEvents`, and every action must start with `logs:`.
- Destination account mismatch must fail before mutation with error substring `account mismatch`.
- Resolver ingress must contain exactly TCP 53 and UDP 53 rules from the current corporate CIDRs in config, using the key `cidr_blocks`.
- Manual resolver rules from observed audit evidence must not be silently deleted. Report them in `drift_report` with `action: "report_only"`, `resource: "resolver_security_group"`, and preserve the observed manual rule details.
- Cumulative behavior from earlier milestones must remain intact: same-AZ app NAT routing, isolated data route tables, gateway endpoints with observed IDs/policies, imported subnet and route-table IDs, top-level `moved` entries, and `outputs.private_app_route_table_ids`.