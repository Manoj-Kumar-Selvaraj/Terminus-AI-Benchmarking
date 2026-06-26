# Dynamic database role contract

The preserved Vault Kubernetes role is `payment-ledger-k8s`. The preserved database role is `payment-ledger`. Each successful issuance operation is identified by `(request_id, pod_uid, vault_role, database_role)`. Replaying an identical operation returns one logical credential. Reusing a request ID with a different pod or role is a conflict.

The runtime returns an opaque `password_reference`; the application never receives or persists the underlying password. The dynamic user can perform only `SELECT_PAYMENT_STATUS`, `INSERT_LEDGER_EVENT`, `UPDATE_RETRY_METADATA`, and `EXECUTE_APPROVED_PROCEDURE` in tenant `payments`. `CREATE_ROLE`, `DROP_TABLE`, `ALTER_TABLE`, `GRANT_PRIVILEGES`, `SELECT_IDENTITY_SECRETS`, and cross-tenant access are forbidden and are checked by executing the simulated database operation.
