# Partner gateway HTTP rate-limit contract

Allowed requests continue to the downstream handler unchanged and include `X-RateLimit-Remaining` with a non-negative decimal value.

Denied requests return HTTP 429 with `Content-Type: application/json`, `Retry-After-Ms`, and the body shape below. `retry_after_ms` is a positive integer and must agree with the response header.

```json
{"code":"rate_limited","retry_after_ms":1000}
```

Requests without an explicit tenant header are still subject to rate limiting through the implicit legacy identity. They must not be rejected with a tenant-validation error.
