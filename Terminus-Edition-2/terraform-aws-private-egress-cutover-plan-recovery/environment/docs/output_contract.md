# Module output contract

The module must expose stable output names consumed by downstream platform automation, including VPC identifiers, subnet maps, route table identifiers, endpoint identifiers, and queue references.

Output values must be derived from created resources and input variables so fixture overrides in isolated workspaces change rendered addresses without source edits.

`egress_route_matrix` is a map keyed by enabled AZ key. Each value is an object with `app_cidr`, `data_cidr`, `nat_az`, and `data_has_default_route`. `nat_az` is the NAT gateway AZ selected for that app route table and must equal the map key for same-AZ routing. `data_has_default_route` is a boolean and must be `false` for isolated data route tables.

`endpoint_services` is the set of interface endpoint service suffixes planned for the runtime: `ecr.api`, `ecr.dkr`, `logs`, `sts`, `secretsmanager`, `kms`, `sqs`, `ssm`, `ssmmessages`, and `ec2messages`. Service names are rendered from `var.region`, not hardcoded region literals.

`security_summary` is an object with `endpoint_ingress_cidrs` and `resolver_ingress_cidrs`. `endpoint_ingress_cidrs` lists the app and data subnet CIDRs admitted to endpoint TCP 443 ingress. `resolver_ingress_cidrs` lists the corporate DNS CIDRs admitted to resolver TCP/UDP 53 ingress.

Subnet flow logs are exposed through `flow_log_group_name` and keyed in configuration as `aws_flow_log.subnet["public-<az>"]`, `aws_flow_log.subnet["app-<az>"]`, and `aws_flow_log.subnet["data-<az>"]`. Runtime queue access is exposed through `runtime_queue_arn`.
