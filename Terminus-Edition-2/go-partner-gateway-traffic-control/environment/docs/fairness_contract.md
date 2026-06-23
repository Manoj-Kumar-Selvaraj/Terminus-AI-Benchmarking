# Traffic-isolation contract

The configured burst and refill rate apply independently to each normalized tenant identity. Tenant identities are normalized by trimming surrounding whitespace and comparing case-insensitively. One tenant exhausting its allowance must not reduce another tenant's allowance.

The limiter remains a token bucket: successful decisions consume one token, denied decisions include a positive retry duration, and elapsed forward time refills up to the configured burst. Keep the exported `limiter.New` and `(*Limiter).Allow` interfaces and the `Decision` fields compatible.
