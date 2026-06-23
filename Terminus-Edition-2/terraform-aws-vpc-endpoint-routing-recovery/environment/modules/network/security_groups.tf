locals {
  endpoint_security_group_rules = jsondecode(<<JSON
{
  "ingress": [
    {
      "description": "incident mitigation temporary open rule",
      "protocol": "tcp",
      "from_port": 443,
      "to_port": 443,
      "cidr_blocks": ["0.0.0.0/0"],
      "ipv6_cidr_blocks": []
    },
    {
      "description": "legacy IPv6 default retained by refactor",
      "protocol": "tcp",
      "from_port": 443,
      "to_port": 443,
      "cidr_blocks": [],
      "ipv6_cidr_blocks": ["::/0"]
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
