One upstream later stalled long enough that clients exceeded the published route-service latency contract. Review `/app/evidence/latency_contract.txt` and the proxy path used by `/route/{tenant}`. A stalled upstream must produce the router's gateway-timeout response within the contract window instead of holding the client connection open.

Preserve all prior behavior: race-free route refresh, cleanup after upstream errors, graceful completion of accepted requests, unchanged health endpoint, `404` for unknown tenants, and normal pass-through of successful upstream responses.
