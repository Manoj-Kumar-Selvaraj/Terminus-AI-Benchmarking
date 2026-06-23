locals {
  gateway_vpc_endpoints = jsondecode(<<JSON
{
  "s3": {
    "id": "vpce-gw-s3",
    "service_name": "com.amazonaws.us-east-1.s3",
    "vpc_endpoint_type": "Gateway",
    "route_table_ids": ["rtb-private-a"]
  },
  "dynamodb": {
    "id": "vpce-gw-dynamodb",
    "service_name": "com.amazonaws.us-east-1.dynamodb",
    "vpc_endpoint_type": "Gateway",
    "route_table_ids": ["rtb-private-a", "rtb-public-a"]
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
