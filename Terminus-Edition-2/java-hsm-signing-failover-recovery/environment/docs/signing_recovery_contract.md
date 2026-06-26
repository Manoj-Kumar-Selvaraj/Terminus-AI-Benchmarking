# Signing Recovery Contract

Each request file contains `id` and `payload`. Request IDs are durable operation identities. Reusing an ID with a different payload digest is a conflict.

Before calling the HSM, the gateway durably records a PREPARED request with its payload digest, selected key, policy generation, and operation ID. The operation ID must remain stable for every retry and recovery of that request.

The local HSM simulator appends one audit row per operation ID to `hsm.log`. A crash can occur after the HSM side effect but before the request is marked COMMITTED. Recovery must consult the HSM audit and finalize that exact signature rather than issuing another operation. A committed retry returns the original signature. Unrelated requests remain independent.

`signerctl recover` processes all non-committed requests under a valid lease and writes a summary report. Re-running recovery must not add HSM audit rows.
