# Lease lifecycle contract

Durable lifecycle states are `REQUESTED`, `DB_USER_CREATED`, `LEASE_ISSUED`, `ACTIVE`, `RENEWING`, `ROTATING`, `REVOKE_PENDING`, `REVOKED`, `EXPIRED`, and `FAILED`. A lease records `lease_id`, `request_id`, `database_username`, `issued_at`, `expires_at`, `renewable`, `max_expires_at`, `generation`, `vault_node`, `owner_pod_uid`, and `status`.

The default TTL is 300 seconds, maximum lifetime is 1800 seconds, renewal window is 90 seconds, minimum renewal interval is 30 seconds, and maximum renewal attempts is four. Time comes from the trusted deterministic clock. Renewal preserves lease ID, request ID, username, owner, and generation. It must never move expiry beyond `max_expires_at`. A valid lease remains usable during bounded transient renewal retry, but expired or revoked credentials are never presented as active.

Renewal maintenance inside the safety window but sooner than `minimumRenewalIntervalSeconds` after the last successful renewal returns action `NO_ACTION` with the existing lease still usable. A runtime clock moving backwards relative to the durable checkpoint is rejected with `CLOCK_REGRESSION`. Durable lease timestamps that cannot be parsed are rejected with `MALFORMED_LEASE` instead of being guessed or overwritten.

The append-only journal is JSON Lines. A torn final line may be discarded during restart recovery; malformed committed interior records are a hard error. Journal and snapshot writes use temporary files and atomic rename. Password material and raw tokens are forbidden from every application-owned state surface.
