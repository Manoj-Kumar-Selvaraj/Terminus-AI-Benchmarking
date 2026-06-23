# Audit Report Schema

`/app/out/audit_report.csv` must use this exact pipe-delimited header:

`audit_id|frame_id|craft_id|channel|service_class|payload_hash|verdict_code|status`

Rules:
- One output row per audit input row in audit-file order.
- `status` is exactly `ACCEPTED` or `REJECTED`.
- `ACCEPTED` rows emit canonical `service_class` from the consumed catalog row.
- `REJECTED` rows leave `service_class` blank.
