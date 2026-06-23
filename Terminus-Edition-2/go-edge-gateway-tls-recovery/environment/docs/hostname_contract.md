# Routed endpoint identity
The TCP connection is made to an address selected by service discovery, but the authenticated service identity is `ledger.service.internal`. The configured `ServerName` is part of the route contract and must be used for certificate verification even when the URL contains a loopback or discovered IP address.
Do not rewrite the request URL merely to influence certificate verification. Do not set `InsecureSkipVerify`.
