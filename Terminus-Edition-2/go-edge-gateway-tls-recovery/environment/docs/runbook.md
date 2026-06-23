# Rotation incident runbook excerpt
1. Confirm the failure class from the gateway handshake log.
2. Compare the configured service identity with the certificate SANs.
3. Validate both issuer populations during the overlap window.
4. Stage renewed client files, invoke the in-process reload hook, and verify a new handshake.
5. Never resolve the incident by disabling verification or globally modifying the host trust store.
