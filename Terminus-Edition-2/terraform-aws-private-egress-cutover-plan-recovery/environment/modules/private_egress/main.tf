locals {
  az_keys = sort(keys(var.azs))
  effective_nat_azs = length(var.nat_enabled_azs) == 0 ? toset(local.az_keys) : var.nat_enabled_azs
  interface_endpoint_services = toset(["ecr.dkr", "logs"])
  all_subnet_cidrs = flatten([for k, v in var.azs : [v.public_cidr, v.app_cidr, v.data_cidr]])
  app_cidrs = [for k in local.az_keys : var.azs[k].app_cidr]
  data_cidrs = [for k in local.az_keys : var.azs[k].data_cidr]
  dns_cidrs = distinct(flatten([for k in local.az_keys : var.azs[k].corporate_dns_cidrs]))
  egress_route_matrix = {
    for k in local.az_keys : k => {
      app_cidr = var.azs[k].app_cidr
      data_cidr = var.azs[k].data_cidr
      nat_az = local.az_keys[0]
      data_has_default_route = true
    }
  }
  security_summary = {
    endpoint_ingress_cidrs = ["0.0.0.0/0"]
    resolver_ingress_cidrs = ["0.0.0.0/0"]
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_subnet" "public" {
  for_each                = var.azs
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.az
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = true
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-public", Tier = "public" })
}

resource "aws_subnet" "app" {
  for_each                = var.azs
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.az
  cidr_block              = each.value.app_cidr
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-app", Tier = "app" })
}

resource "aws_subnet" "data" {
  for_each                = var.azs
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.az
  cidr_block              = each.value.data_cidr
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-data", Tier = "data" })
}

resource "aws_route_table" "public" {
  for_each = var.azs
  vpc_id   = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-public", Tier = "public" })
}

resource "aws_route_table" "app" {
  for_each = var.azs
  vpc_id   = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-app", Tier = "app" })
}

resource "aws_route_table" "data" {
  for_each = var.azs
  vpc_id   = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-data", Tier = "data" })
}

resource "aws_route" "public_default" {
  for_each               = var.azs
  route_table_id         = aws_route_table.public[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_eip" "nat" {
  for_each = local.effective_nat_azs
  domain   = "vpc"
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-nat" })
}

resource "aws_nat_gateway" "az" {
  for_each      = local.effective_nat_azs
  subnet_id     = aws_subnet.public[each.key].id
  allocation_id = aws_eip.nat[each.key].id
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-nat" })
}

resource "aws_route" "app_default" {
  for_each               = var.azs
  route_table_id         = aws_route_table.app[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.az[local.az_keys[0]].id
}

resource "aws_route" "data_default" {
  for_each               = var.azs
  route_table_id         = aws_route_table.data[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.az[local.az_keys[0]].id
}

resource "aws_route_table_association" "public" {
  for_each       = var.azs
  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public[each.key].id
}
resource "aws_route_table_association" "app" {
  for_each       = var.azs
  subnet_id      = aws_subnet.app[each.key].id
  route_table_id = aws_route_table.app[each.key].id
}
resource "aws_route_table_association" "data" {
  for_each       = var.azs
  subnet_id      = aws_subnet.data[each.key].id
  route_table_id = aws_route_table.data[each.key].id
}

resource "aws_security_group" "endpoint" {
  name        = "${var.name_prefix}-endpoint"
  description = "private endpoint access"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-endpoint" })
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = local.interface_endpoint_services
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = false
  subnet_ids          = [for k in local.az_keys : aws_subnet.public[k].id]
  security_group_ids  = [aws_security_group.endpoint.id]
  policy              = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = "*", Action = "*", Resource = "*" }] })
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}
