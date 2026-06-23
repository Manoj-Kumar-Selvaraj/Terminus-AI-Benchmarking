# This fixture models a downstream stack that cannot be edited during the
# network module recovery. It still consumes the legacy output names.
locals {
  expected_vpc_id                     = module.network.vpc_id
  expected_private_subnet_ids          = module.network.private_subnet_ids
  expected_endpoint_security_group_ids = module.network.endpoint_security_group_ids
  expected_gateway_endpoint_ids        = module.network.gateway_vpc_endpoint_ids
  expected_interface_endpoint_ids      = module.network.interface_vpc_endpoint_ids
}
