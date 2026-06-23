locals {
  # Refactor manifest for subnet association and default route intent. The
  # inspector derives behavior from the route table IDs and subnet IDs, not from
  # these map labels alone.
  route_table_associations = jsondecode(<<JSON
{
  "subnet-public-a": "rtb-public-a",
  "subnet-public-b": "rtb-public-b",
  "subnet-private-a": "rtb-public-a",
  "subnet-private-b": "rtb-private-a"
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
  "public-a-leak": {
    "route_table_id": "rtb-public-a",
    "destination_cidr_block": "0.0.0.0/0",
    "nat_gateway_id": "nat-a"
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
