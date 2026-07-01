# Milestone 2 — restore Private Endpoint DNS cutover

Continue the same module recovery. The plan review shows private endpoints being created without deterministic Private DNS zone attachment, so Storage and Key Vault names could resolve through public records after cutover. Keep the Milestone 1 behavior and generate the Blob, Queue, Key Vault and Azure Database for PostgreSQL Private DNS zones from a local catalog rather than from hard-coded Azure resource IDs.

Each zone must link to the spoke VNet with registration disabled, each entry in `var.private_endpoints` must create a private endpoint only in `var.private_endpoint_subnet_key`, and every endpoint must have a `private_dns_zone_group` that references the managed zone catalog. Disable private endpoint network policies only for the private endpoint subnet and preserve the Private DNS zone and private endpoint outputs without embedding subscription IDs, provider resource IDs or existing DNS zone IDs inside the module.
