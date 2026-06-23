# Tenant route service contract

The router accepts `GET /route/{tenant}` and forwards the request to the
currently active upstream for that tenant. Operators can refresh tenant routes
while the process is serving traffic; live refresh must not require a process
restart.

For release train 2026.06, accepted requests must be allowed to finish during
termination unless the caller's own context expires. A downstream that stalls
past the published route SLO must produce a gateway timeout response instead of
holding the client connection open.
