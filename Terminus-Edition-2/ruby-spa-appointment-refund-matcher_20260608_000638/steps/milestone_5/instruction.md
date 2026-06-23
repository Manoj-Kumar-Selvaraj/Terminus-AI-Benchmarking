Extend `/app/lib/reconcile.rb` with client refund limits from `/app/config/client_limits.csv` while
keeping all previous behavior. The limits file is header-addressed and includes `client_id`,
`service_area`, `max_refund_cents`, `enabled`, and optional `allow_any` columns; extra columns are
ignored. Trim all fields. A row is well formed only when `client_id` is nonblank, `service_area`
canonicalizes through the runtime alias map to `MASSAGE`, `FACIAL`, or `SAUNA`, `max_refund_cents`
is a positive base-10 integer, and `enabled` is `true` or `false` case-insensitively. If `allow_any`
is present it must be `true` or `false`; if it is absent, treat it as `false`. The last well-formed
row for a `(client_id, canonical service_area)` key is authoritative.

After an appointment
candidate has been selected by the prior rules, the candidate must also have an enabled exact
client/service limit row and the refund amount must be less than or equal to `max_refund_cents`. For
`ANY` refund rows, the selected service must also have `allow_any = true`. Missing, disabled,
malformed, wrong-client, wrong-service, or over-limit policies make the refund unmatched and must
not consume the appointment row. Client limits do not bypass any prior identity, amount, alias,
service-policy, date, status, or consumption gate. Preserve all report and summary contracts.
