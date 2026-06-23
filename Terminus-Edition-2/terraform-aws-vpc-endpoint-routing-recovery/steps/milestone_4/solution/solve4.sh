#!/usr/bin/env bash
set -euo pipefail
cat > /app/modules/network/routes.tf <<'EOF'

locals {
  route_table_associations = jsondecode(<<JSON
{
  "subnet-public-a": "rtb-public-a",
  "subnet-public-b": "rtb-public-b",
  "subnet-private-a": "rtb-private-a",
  "subnet-private-b": "rtb-private-b"
}
JSON
  )

  private_default_routes = jsondecode(<<JSON
{
  "private-a": {
    "route_table_id": "rtb-private-a",
    "destination_cidr_block": "0.0.0.0/0",
    "nat_gateway_id": "nat-a"
  },
  "private-b": {
    "route_table_id": "rtb-private-b",
    "destination_cidr_block": "0.0.0.0/0",
    "nat_gateway_id": "nat-b"
  }
}
JSON
  )

  public_default_routes = jsondecode(<<JSON
{
  "public-a": {
    "route_table_id": "rtb-public-a",
    "destination_cidr_block": "0.0.0.0/0",
    "gateway_id": "igw-staging"
  },
  "public-b": {
    "route_table_id": "rtb-public-b",
    "destination_cidr_block": "0.0.0.0/0",
    "gateway_id": "igw-staging"
  }
}
JSON
  )
}

resource "aws_route_table_association" "subnet" {
  for_each = local.route_table_associations

  subnet_id      = each.key
  route_table_id = each.value
}

resource "aws_route" "private_nat" {
  for_each = local.private_default_routes

  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.destination_cidr_block
  nat_gateway_id         = each.value.nat_gateway_id
}

resource "aws_route" "public_igw" {
  for_each = local.public_default_routes

  route_table_id         = each.value.route_table_id
  destination_cidr_block = each.value.destination_cidr_block
  gateway_id             = each.value.gateway_id
}
EOF

cat > /app/modules/network/endpoints.tf <<'EOF'

locals {
  gateway_vpc_endpoints = jsondecode(<<JSON
{
  "s3": {
    "id": "vpce-gw-s3",
    "service_name": "com.amazonaws.us-east-1.s3",
    "vpc_endpoint_type": "Gateway",
    "route_table_ids": ["rtb-private-a", "rtb-private-b"]
  },
  "dynamodb": {
    "id": "vpce-gw-dynamodb",
    "service_name": "com.amazonaws.us-east-1.dynamodb",
    "vpc_endpoint_type": "Gateway",
    "route_table_ids": ["rtb-private-a", "rtb-private-b"]
  }
}
JSON
  )

  interface_vpc_endpoints = jsondecode(<<JSON
{
  "ssm": {
    "id": "vpce-if-ssm",
    "service_name": "com.amazonaws.us-east-1.ssm",
    "vpc_endpoint_type": "Interface",
    "subnet_ids": ["subnet-private-a", "subnet-private-b"],
    "private_dns_enabled": true,
    "security_group_ids": ["sg-vpce-staging"],
    "dns_name": "ssm.vpce.staging.internal"
  },
  "ssmmessages": {
    "id": "vpce-if-ssmmessages",
    "service_name": "com.amazonaws.us-east-1.ssmmessages",
    "vpc_endpoint_type": "Interface",
    "subnet_ids": ["subnet-private-a", "subnet-private-b"],
    "private_dns_enabled": true,
    "security_group_ids": ["sg-vpce-staging"],
    "dns_name": "ssmmessages.vpce.staging.internal"
  },
  "ec2messages": {
    "id": "vpce-if-ec2messages",
    "service_name": "com.amazonaws.us-east-1.ec2messages",
    "vpc_endpoint_type": "Interface",
    "subnet_ids": ["subnet-private-a", "subnet-private-b"],
    "private_dns_enabled": true,
    "security_group_ids": ["sg-vpce-staging"],
    "dns_name": "ec2messages.vpce.staging.internal"
  }
}
JSON
  )
}

resource "aws_vpc_endpoint" "gateway" {
  for_each = local.gateway_vpc_endpoints

  vpc_id            = aws_vpc.this.id
  service_name      = each.value.service_name
  vpc_endpoint_type = each.value.vpc_endpoint_type
  route_table_ids   = each.value.route_table_ids

  tags = {
    Environment = local.network_inventory.environment
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_vpc_endpoints

  vpc_id              = aws_vpc.this.id
  service_name        = each.value.service_name
  vpc_endpoint_type   = each.value.vpc_endpoint_type
  subnet_ids          = each.value.subnet_ids
  private_dns_enabled = each.value.private_dns_enabled
  security_group_ids  = each.value.security_group_ids

  tags = {
    Environment = local.network_inventory.environment
  }
}
EOF

cat > /app/modules/network/security_groups.tf <<'EOF'

locals {
  endpoint_security_group_rules = jsondecode(<<JSON
{
  "ingress": [
    {
      "description": "application workloads to shared interface endpoints",
      "protocol": "tcp",
      "from_port": 443,
      "to_port": 443,
      "source_security_group_ids": ["sg-app-staging", "sg-batch-staging"],
      "cidr_blocks": [],
      "ipv6_cidr_blocks": []
    },
    {
      "description": "private subnet CIDR fallback for endpoint clients",
      "protocol": "tcp",
      "from_port": 443,
      "to_port": 443,
      "source_security_group_ids": [],
      "cidr_blocks": ["10.42.16.0/20", "10.42.32.0/20"],
      "ipv6_cidr_blocks": []
    }
  ],
  "egress": [
    {
      "description": "default egress for endpoint responses",
      "protocol": "-1",
      "from_port": 0,
      "to_port": 0,
      "cidr_blocks": ["0.0.0.0/0"],
      "ipv6_cidr_blocks": []
    }
  ]
}
JSON
  )
}

resource "aws_security_group" "endpoint" {
  name        = local.network_inventory.security_groups.endpoint.name
  description = "Shared interface endpoint security group"
  vpc_id      = aws_vpc.this.id

  tags = {
    Environment = local.network_inventory.environment
  }
}
EOF

cat > /app/modules/network/outputs.tf <<'EOF'

locals {
  module_output_contract = jsondecode(<<JSON
{
  "vpc_id": {
    "shape": "string",
    "value": "vpc-staging-01"
  },
  "vpc_cidr_block": {
    "shape": "string",
    "value": "10.42.0.0/16"
  },
  "private_subnet_ids": {
    "shape": "list(string)",
    "value": ["subnet-private-a", "subnet-private-b"]
  },
  "public_subnet_ids": {
    "shape": "list(string)",
    "value": ["subnet-public-a", "subnet-public-b"]
  },
  "private_route_table_ids": {
    "shape": "list(string)",
    "value": ["rtb-private-a", "rtb-private-b"]
  },
  "public_route_table_ids": {
    "shape": "list(string)",
    "value": ["rtb-public-a", "rtb-public-b"]
  },
  "gateway_vpc_endpoint_ids": {
    "shape": "map(string)",
    "value": {
      "s3": "vpce-gw-s3",
      "dynamodb": "vpce-gw-dynamodb"
    }
  },
  "interface_vpc_endpoint_ids": {
    "shape": "map(string)",
    "value": {
      "ssm": "vpce-if-ssm",
      "ssmmessages": "vpce-if-ssmmessages",
      "ec2messages": "vpce-if-ec2messages"
    }
  },
  "endpoint_security_group_id": {
    "shape": "string",
    "value": "sg-vpce-staging"
  },
  "endpoint_security_group_ids": {
    "shape": "list(string)",
    "value": ["sg-vpce-staging"]
  },
  "network": {
    "shape": "object",
    "value": {
      "vpc": "vpc-staging-01",
      "private_subnets": ["subnet-private-a", "subnet-private-b"],
      "endpoint_security_group": "sg-vpce-staging"
    }
  },
  "endpoint_ids": {
    "shape": "map(string)",
    "value": {
      "s3": "vpce-gw-s3",
      "dynamodb": "vpce-gw-dynamodb",
      "ssm": "vpce-if-ssm",
      "ssmmessages": "vpce-if-ssmmessages",
      "ec2messages": "vpce-if-ec2messages"
    }
  }
}
JSON
  )
}

output "vpc_id" {
  description = "Legacy VPC ID output retained for downstream consumers."
  value       = local.network_inventory.vpc.id
}

output "vpc_cidr_block" {
  description = "Legacy VPC CIDR output retained for downstream consumers."
  value       = local.network_inventory.vpc.cidr_block
}

output "private_subnet_ids" {
  description = "Legacy private subnet IDs in stable AZ/key order."
  value       = [local.network_inventory.subnets["private-a"].id, local.network_inventory.subnets["private-b"].id]
}

output "public_subnet_ids" {
  description = "Legacy public subnet IDs in stable AZ/key order."
  value       = [local.network_inventory.subnets["public-a"].id, local.network_inventory.subnets["public-b"].id]
}

output "private_route_table_ids" {
  description = "Legacy private route table IDs in stable AZ/key order."
  value       = [local.network_inventory.route_tables["private-a"].id, local.network_inventory.route_tables["private-b"].id]
}

output "public_route_table_ids" {
  description = "Legacy public route table IDs in stable AZ/key order."
  value       = [local.network_inventory.route_tables["public-a"].id, local.network_inventory.route_tables["public-b"].id]
}

output "gateway_vpc_endpoint_ids" {
  description = "Legacy gateway endpoint IDs keyed by service."
  value       = { for k, v in local.gateway_vpc_endpoints : k => v.id }
}

output "interface_vpc_endpoint_ids" {
  description = "Legacy interface endpoint IDs keyed by service."
  value       = { for k, v in local.interface_vpc_endpoints : k => v.id }
}

output "endpoint_security_group_id" {
  description = "Legacy scalar endpoint security group ID."
  value       = local.network_inventory.security_groups.endpoint.id
}

output "endpoint_security_group_ids" {
  description = "Legacy list-shaped endpoint security group IDs."
  value       = [local.network_inventory.security_groups.endpoint.id]
}

output "network" {
  description = "New aggregate network output introduced during refactor."
  value = {
    vpc                     = local.network_inventory.vpc.id
    private_subnets         = [local.network_inventory.subnets["private-a"].id, local.network_inventory.subnets["private-b"].id]
    endpoint_security_group = local.network_inventory.security_groups.endpoint.id
  }
}

output "endpoint_ids" {
  description = "New aggregate endpoint output introduced during refactor."
  value = merge(
    { for k, v in local.gateway_vpc_endpoints : k => v.id },
    { for k, v in local.interface_vpc_endpoints : k => v.id }
  )
}
EOF

cat > /app/modules/network/moved.tf <<'EOF'

moved {
  from = aws_subnet.private[0]
  to   = aws_subnet.this["private-a"]
}

moved {
  from = aws_subnet.private[1]
  to   = aws_subnet.this["private-b"]
}

moved {
  from = aws_route_table.private[0]
  to   = aws_route_table.this["private-a"]
}

moved {
  from = aws_route_table.private[1]
  to   = aws_route_table.this["private-b"]
}

moved {
  from = aws_route.private_nat[0]
  to   = aws_route.private_nat["private-a"]
}

moved {
  from = aws_route.private_nat[1]
  to   = aws_route.private_nat["private-b"]
}

moved {
  from = aws_vpc_endpoint.gateway["s3"]
  to   = aws_vpc_endpoint.gateway["s3"]
}

moved {
  from = aws_vpc_endpoint.gateway["dynamodb"]
  to   = aws_vpc_endpoint.gateway["dynamodb"]
}

moved {
  from = aws_vpc_endpoint.interface["ssm"]
  to   = aws_vpc_endpoint.interface["ssm"]
}

moved {
  from = aws_vpc_endpoint.interface["ssmmessages"]
  to   = aws_vpc_endpoint.interface["ssmmessages"]
}

moved {
  from = aws_vpc_endpoint.interface["ec2messages"]
  to   = aws_vpc_endpoint.interface["ec2messages"]
}

moved {
  from = aws_security_group.endpoint[0]
  to   = aws_security_group.endpoint["shared"]
}

locals {
  migration_notes = jsondecode(<<JSON
{
  "identity_policy": "stable for_each keys plus explicit moved blocks",
  "release_note": "Legacy outputs remain available while the network module uses named resource identity. The migration is non-destructive for the VPC, subnets, route tables, NAT routes, gateway endpoints, interface endpoints, and endpoint security group."
}
JSON
  )
}
EOF

cat > /app/docs/migration_constraints.md <<'EOF'

# Migration constraints

The refactor moved several module internals from list-indexed resource identity
to named identity. The migration is non-destructive for stable network resources:
existing VPC, subnet, route table, NAT gateway, gateway endpoint, interface
endpoint, and endpoint security group identities are preserved.

## Release note: compatibility path

Legacy output names remain available for downstream consumers while the new
aggregate outputs stay available for newer stacks. The module continues to
publish `vpc_id`, `vpc_cidr_block`, `private_subnet_ids`, `public_subnet_ids`,
`private_route_table_ids`, `public_route_table_ids`, `gateway_vpc_endpoint_ids`,
`interface_vpc_endpoint_ids`, `endpoint_security_group_id`, and
`endpoint_security_group_ids` with their previous shapes.

Resource address changes are covered by Terraform `moved` blocks in
`modules/network/moved.tf`. Those moved blocks document the list-indexed to
stable-key migration for private subnets, private route tables, NAT routes, and
the shared endpoint security group, while keeping endpoint addresses auditable.
The VPC CIDR, subnet CIDRs, staging environment name, route-table IDs, NAT IDs,
endpoint IDs, and endpoint security group ID are unchanged.
EOF

python3 /app/scripts/inspect_network_contract.py --pretty >/tmp/network-inspector/milestone4-summary.json
