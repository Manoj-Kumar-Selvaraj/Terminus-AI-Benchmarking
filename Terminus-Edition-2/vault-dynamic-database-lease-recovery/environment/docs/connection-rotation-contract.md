# Connection rotation contract

A safe rotation validates the new credential, creates a candidate pool, verifies readiness, atomically publishes one active generation for the pod, prevents new work on the retired generation, drains documented in-flight sessions, and then revokes the old lease. A failed candidate cannot displace a healthy active pool. A crash after the swap is recovered by retaining the new healthy generation and completing old-lease cleanup. A failed revocation is isolated in `REVOKE_PENDING`; it does not block cleanup for other leases.

The static break-glass reference remains documented for operators but must never be selected by the application workflow. If no valid dynamic credential exists, security takes priority and the API becomes safely unavailable.
