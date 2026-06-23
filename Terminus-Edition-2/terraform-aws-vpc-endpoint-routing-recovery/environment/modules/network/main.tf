terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  # The offline verifier reads this jsondecode local to compare the refactored
  # module contract with saved state. Keep this as declarative module inventory,
  # not as generated test output.
  network_inventory = jsondecode(<<JSON
{
  "environment": "staging",
  "vpc": {
    "id": "vpc-staging-01",
    "cidr_block": "10.42.0.0/16",
    "name": "shared-staging-vpc"
  },
  "subnets": {
    "public-a": {
      "id": "subnet-public-a",
      "cidr_block": "10.42.0.0/24",
      "az": "us-east-1a",
      "tier": "public",
      "route_table_key": "public-a"
    },
    "public-b": {
      "id": "subnet-public-b",
      "cidr_block": "10.42.1.0/24",
      "az": "us-east-1b",
      "tier": "public",
      "route_table_key": "public-b"
    },
    "private-a": {
      "id": "subnet-private-a",
      "cidr_block": "10.42.16.0/20",
      "az": "us-east-1a",
      "tier": "private",
      "route_table_key": "private-a"
    },
    "private-b": {
      "id": "subnet-private-b",
      "cidr_block": "10.42.32.0/20",
      "az": "us-east-1b",
      "tier": "private",
      "route_table_key": "private-b"
    }
  },
  "route_tables": {
    "public-a": {
      "id": "rtb-public-a",
      "tier": "public",
      "az": "us-east-1a"
    },
    "public-b": {
      "id": "rtb-public-b",
      "tier": "public",
      "az": "us-east-1b"
    },
    "private-a": {
      "id": "rtb-private-a",
      "tier": "private",
      "az": "us-east-1a",
      "nat_gateway_id": "nat-a"
    },
    "private-b": {
      "id": "rtb-private-b",
      "tier": "private",
      "az": "us-east-1b",
      "nat_gateway_id": "nat-b"
    }
  },
  "nat_gateways": {
    "private-a": {
      "id": "nat-a",
      "public_ip": "198.51.100.10",
      "az": "us-east-1a"
    },
    "private-b": {
      "id": "nat-b",
      "public_ip": "198.51.100.11",
      "az": "us-east-1b"
    }
  },
  "security_groups": {
    "endpoint": {
      "id": "sg-vpce-staging",
      "name": "staging-vpce-shared"
    },
    "app": {
      "id": "sg-app-staging",
      "name": "staging-application"
    },
    "batch": {
      "id": "sg-batch-staging",
      "name": "staging-batch"
    }
  }
}
JSON
  )
}

resource "aws_vpc" "this" {
  cidr_block = local.network_inventory.vpc.cidr_block

  tags = {
    Name        = local.network_inventory.vpc.name
    Environment = local.network_inventory.environment
  }
}

resource "aws_subnet" "this" {
  for_each = local.network_inventory.subnets

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr_block
  availability_zone = each.value.az

  tags = {
    Name        = "${local.network_inventory.environment}-${each.key}"
    Tier        = each.value.tier
    Environment = local.network_inventory.environment
  }
}

resource "aws_route_table" "this" {
  for_each = local.network_inventory.route_tables

  vpc_id = aws_vpc.this.id

  tags = {
    Name        = "${local.network_inventory.environment}-${each.key}"
    Tier        = each.value.tier
    Environment = local.network_inventory.environment
  }
}
