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
    "subnet_ids": ["subnet-private-a", "subnet-public-b"],
    "private_dns_enabled": false,
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
    "subnet_ids": ["subnet-public-a"],
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

python3 /app/scripts/inspect_network_contract.py --pretty >/tmp/network-inspector/milestone2-summary.json
