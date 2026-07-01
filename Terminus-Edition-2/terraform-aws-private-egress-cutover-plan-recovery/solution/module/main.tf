locals {
  az_keys = sort(keys(var.azs))
  effective_nat_azs = length(var.nat_enabled_azs) == 0 ? toset(local.az_keys) : var.nat_enabled_azs
  nat_coverage_missing = setsubtract(toset(local.az_keys), local.effective_nat_azs)

  egress_route_matrix = {
    for k in local.az_keys : k => {
      app_cidr               = var.azs[k].app_cidr
      data_cidr              = var.azs[k].data_cidr
      nat_az                 = k
      data_has_default_route = false
    }
  }

  interface_endpoint_services = toset([
    "ecr.api",
    "ecr.dkr",
    "logs",
    "sts",
    "secretsmanager",
    "kms",
    "sqs",
    "ssm",
    "ssmmessages",
    "ec2messages",
  ])
  gateway_endpoint_services = toset(["s3", "dynamodb"])

  interface_endpoint_actions = {
    "ecr.api"        = ["ecr:GetAuthorizationToken", "ecr:DescribeRepositories"]
    "ecr.dkr"        = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    "logs"           = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    "sts"            = ["sts:AssumeRole", "sts:GetCallerIdentity"]
    "secretsmanager" = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    "kms"            = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    "sqs"            = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    "ssm"            = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    "ssmmessages"    = ["ssmmessages:CreateControlChannel", "ssmmessages:OpenControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenDataChannel"]
    "ec2messages"    = ["ec2messages:AcknowledgeMessage", "ec2messages:GetMessages", "ec2messages:SendReply"]
  }

  app_cidrs  = [for k in local.az_keys : var.azs[k].app_cidr]
  data_cidrs = [for k in local.az_keys : var.azs[k].data_cidr]
  workload_cidrs = concat(local.app_cidrs, local.data_cidrs)
  dns_cidrs = sort(distinct(flatten([for k in local.az_keys : var.azs[k].corporate_dns_cidrs])))
  security_summary = {
    endpoint_ingress_cidrs = sort(local.workload_cidrs)
    resolver_ingress_cidrs = local.dns_cidrs
  }

  all_subnets = merge(
    { for k in local.az_keys : "public-${k}" => aws_subnet.public[k].id },
    { for k in local.az_keys : "app-${k}" => aws_subnet.app[k].id },
    { for k in local.az_keys : "data-${k}" => aws_subnet.data[k].id }
  )
}

moved {
  from = aws_subnet.private["use1a"]
  to   = aws_subnet.app["use1a"]
}
moved {
  from = aws_subnet.private["use1b"]
  to   = aws_subnet.app["use1b"]
}
moved {
  from = aws_subnet.private["use1c"]
  to   = aws_subnet.app["use1c"]
}
moved {
  from = aws_route_table.private["use1a"]
  to   = aws_route_table.app["use1a"]
}
moved {
  from = aws_route_table.private["use1b"]
  to   = aws_route_table.app["use1b"]
}
moved {
  from = aws_route_table.private["use1c"]
  to   = aws_route_table.app["use1c"]
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = merge(var.tags, { Name = "${var.name_prefix}-vpc" })

  lifecycle {
    precondition {
      condition     = length(local.nat_coverage_missing) == 0
      error_message = "Every app subnet AZ must have a same-AZ NAT gateway; cross-AZ fallback is not allowed."
    }
  }
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
  nat_gateway_id         = aws_nat_gateway.az[each.key].id
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
    cidr_blocks = local.workload_cidrs
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
  private_dns_enabled = true
  subnet_ids          = [for k in local.az_keys : aws_subnet.app[k].id]
  security_group_ids  = [aws_security_group.endpoint.id]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RuntimeAccessOnly"
      Effect    = "Allow"
      Principal = { AWS = var.allowed_principal_arns }
      Action    = local.interface_endpoint_actions[each.key]
      Resource  = ["arn:aws:${split(".", each.key)[0]}:${var.region}:${var.account_id}:*"]
    }]
  })
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}

resource "aws_vpc_endpoint" "gateway" {
  for_each          = local.gateway_endpoint_services
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type = "Gateway"
  route_table_ids = concat(
    [for k in local.az_keys : aws_route_table.app[k].id],
    [for k in local.az_keys : aws_route_table.data[k].id]
  )
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "ArtifactReadOnly"
      Effect    = "Allow"
      Principal = { AWS = var.allowed_principal_arns }
      Action    = each.key == "s3" ? ["s3:GetObject", "s3:ListBucket"] : ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:DescribeTable"]
      Resource  = each.key == "s3" ? var.artifact_bucket_arns : ["arn:aws:dynamodb:${var.region}:${var.account_id}:table/payments-*"]
    }]
  })
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}

resource "aws_security_group" "resolver" {
  name        = "${var.name_prefix}-resolver"
  description = "corporate DNS resolver ingress"
  vpc_id      = aws_vpc.this.id
  ingress {
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = local.dns_cidrs
  }
  ingress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = local.dns_cidrs
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-resolver" })
}

resource "aws_kms_key" "logs" {
  description             = "${var.name_prefix} runtime and flow log encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RuntimePrincipals"
      Effect    = "Allow"
      Principal = { AWS = concat(var.allowed_principal_arns, ["arn:aws:iam::${var.account_id}:root"]) }
      Action    = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
      Resource  = "*"
    }]
  })
  tags = merge(var.tags, { Name = "${var.name_prefix}-logs" })
  lifecycle { prevent_destroy = true }
}

resource "aws_cloudwatch_log_group" "flow" {
  name              = "/aws/vpc/${var.name_prefix}/flow"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.logs.arn
  tags = merge(var.tags, { Name = "${var.name_prefix}-flow" })
  lifecycle { prevent_destroy = true }
}

resource "aws_iam_role" "flow_logs" {
  name = "${var.name_prefix}-flow-logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "flow_logs" {
  name = "${var.name_prefix}-flow-logs"
  role = aws_iam_role.flow_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogGroups", "logs:DescribeLogStreams"]
      Resource = "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/vpc/${var.name_prefix}/flow:*"
    }]
  })
}

resource "aws_flow_log" "subnet" {
  for_each             = local.all_subnets
  iam_role_arn         = aws_iam_role.flow_logs.arn
  log_destination      = aws_cloudwatch_log_group.flow.arn
  traffic_type         = "ALL"
  subnet_id            = each.value
  log_destination_type = "cloud-watch-logs"
  log_format           = "$${interface-id} $${srcaddr} $${dstaddr} $${srcport} $${dstport} $${protocol} $${action} $${log-status}"
  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}-flow" })
}

resource "aws_sqs_queue" "runtime" {
  name                              = var.runtime_queue_name
  kms_master_key_id                 = aws_kms_key.logs.arn
  kms_data_key_reuse_period_seconds = 300
  tags = merge(var.tags, { Name = var.runtime_queue_name })
}

resource "aws_sqs_queue_policy" "runtime" {
  queue_url = aws_sqs_queue.runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowRuntimeThroughEndpoint"
        Effect    = "Allow"
        Principal = { AWS = var.allowed_principal_arns }
        Action    = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource  = aws_sqs_queue.runtime.arn
        Condition = { StringEquals = { "aws:SourceVpce" = aws_vpc_endpoint.interface["sqs"].id } }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource  = aws_sqs_queue.runtime.arn
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenyOutsideEndpoint"
        Effect    = "Deny"
        Principal = "*"
        Action    = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource  = aws_sqs_queue.runtime.arn
        Condition = { StringNotEquals = { "aws:SourceVpce" = aws_vpc_endpoint.interface["sqs"].id } }
      }
    ]
  })
}
