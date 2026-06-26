# Payment ledger credential incident timeline

- 09:00 UTC: database-role migration begins; new pods report successful issuance.
- 09:11 UTC: namespace `payments-preview` is observed using the payment role.
- 09:17 UTC: first long-running pod starts PostgreSQL authentication failures after a delayed renewal.
- 09:24 UTC: operators see lease expiry extended beyond the role's 30-minute maximum.
- 09:31 UTC: emergency static credential reference is added to pool configuration.
- 09:38 UTC: revoked Vault leases still have active PostgreSQL users and sessions.
- 09:46 UTC: active Vault node changes during an issuance retry; duplicate users appear for one request.
- 09:54 UTC: a restarted pod loses the lease it owned and requests another credential.
- 10:03 UTC: one failed DROP/disable operation blocks cleanup of unrelated users.
- 10:12 UTC: rollout is paused with old and new client protocols running together.
