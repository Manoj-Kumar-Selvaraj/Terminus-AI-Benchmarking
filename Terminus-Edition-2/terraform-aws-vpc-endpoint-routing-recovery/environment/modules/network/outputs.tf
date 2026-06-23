locals {
  # Downstream compatibility is currently incomplete after the refactor: only
  # new aggregate-style names were kept here.
  module_output_contract = jsondecode(<<JSON
{
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
      "ssm": "vpce-if-ssm"
    }
  }
}
JSON
  )
}

output "network" {
  description = "New aggregate network output introduced during refactor."
  value = {
    vpc                     = local.network_inventory.vpc.id
    private_subnets         = [for k, v in local.network_inventory.subnets : v.id if v.tier == "private"]
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
