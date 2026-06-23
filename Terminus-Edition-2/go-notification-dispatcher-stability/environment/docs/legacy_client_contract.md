# Legacy Webhook Compatibility

Client `legacy-v1` uses the flat version-1 webhook schema represented by
`/app/samples/legacy_webhook_request.json`.

For every initial or retry attempt sent to this client:

- the JSON object contains exactly `account_id`, `amount`, and `event_type`;
- modern envelope fields such as `schema_version`, `trace_id`, and nested `fields` are absent;
- internal payload extensions are not forwarded;
- the request remains valid JSON and uses `Content-Type: application/json`;
- the same `Idempotency-Key` is used on all attempts.

All other client IDs use the modern version-2 envelope documented by
`/app/samples/modern_webhook_request.json`. Compatibility is defined by JSON structure and values, not object-member byte order.
