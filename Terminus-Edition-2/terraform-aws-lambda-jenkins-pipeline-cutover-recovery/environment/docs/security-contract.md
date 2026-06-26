# Security and Non-Destructive Migration Contract

The migration must not introduce static AWS access keys, Jenkins passwords, wildcard Lambda invoke principals, wildcard IAM actions, or direct writes to trusted runtime state.

The Go handlers and controller may be refactored, but the CLI, twelve stage names, event schemas, Terraform module source, DynamoDB key contracts, and versioned alias behavior must remain compatible.

Infrastructure recovery must not destroy checkpoint or effect-ledger tables, delete completed execution history, or disable failure injection and retry behavior.
