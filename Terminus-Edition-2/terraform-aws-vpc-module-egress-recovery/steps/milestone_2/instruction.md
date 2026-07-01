# Gateway endpoint association recovery

Preserve all Milestone 1 behavior. Extend `vpc-recover` to reconcile gateway endpoint ownership from desired config, observed endpoint evidence, and the recovered private app route tables.

Requirements:

- Only `s3` and `dynamodb` gateway endpoints are supported.
- Endpoint reconciliation must follow the endpoint `service` name, not the order of services in config.
- Endpoint associations must include only private app route tables, and each endpoint must have unique `route_table_ids`.
- The recovered state must include `outputs.private_app_route_table_ids` as the list of recovered private app route table IDs. This output must match the app-tier route tables in `route_tables` and must be used for gateway endpoint associations.
- Existing endpoint IDs, endpoint policy documents, endpoint tags, policy account provenance, and metadata must be preserved when safe.
- Existing endpoint policy account values must match the configured workload/account contract. An account mismatch must fail closed with error substring `account mismatch`.
- Unsupported endpoint services must fail before writing or replacing recovered state, with error substring `unsupported`.
- The same fail-before-mutation behavior applies to both `apply` and `resume`; if validation fails, do not leave a new `/app/state/vpc_recovered_state.json`.
- Repeated `apply` must be idempotent and must not duplicate endpoint route-table associations.
- Milestone 1 routing recovery must remain intact: app route tables use same-AZ healthy NAT gateways, and data route tables do not keep module-owned default internet routes.