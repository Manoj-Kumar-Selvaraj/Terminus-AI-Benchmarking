# Legacy identity and HTTP contract

Requests with a non-blank `X-Tenant-ID` use a case-insensitive, whitespace-trimmed explicit tenant identity. Requests whose header is absent or blank use one shared implicit legacy identity and must continue through normal rate limiting rather than returning `tenant_required`.

The implicit legacy identity is distinct from every explicit tenant value, including the literal header `legacy-default`. Denied requests return HTTP 429 as JSON with exactly `code` and `retry_after_ms`, set `Retry-After-Ms` to the same positive integer, and do not invoke the downstream handler. Allowed requests reach the existing handler and retain its response.
