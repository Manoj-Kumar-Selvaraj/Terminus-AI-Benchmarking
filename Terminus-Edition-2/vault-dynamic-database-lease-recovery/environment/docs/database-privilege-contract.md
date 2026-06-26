# Database privilege contract

Allowed operations for the dynamic payment role are:

- `SELECT_PAYMENT_STATUS`
- `INSERT_LEDGER_EVENT`
- `UPDATE_RETRY_METADATA`
- `EXECUTE_APPROVED_PROCEDURE`

The role cannot create roles, alter or drop schema objects, grant privileges, read `identity_secrets`, or address a tenant other than `payments`. Authorization is enforced by the trusted runtime for every operation. A policy-file string match is not proof of access. Expired and revoked users fail new authentication. Existing sessions opened before a pool drain may finish only until the configured 45-second grace deadline.
