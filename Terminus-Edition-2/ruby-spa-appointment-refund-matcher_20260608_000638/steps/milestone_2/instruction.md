Extend `/app/lib/reconcile.rb` for runtime service aliases while keeping all previous behavior. Read
`/app/config/service_aliases.csv` when present. It is header-addressed and contains `alias`,
`canonical`, and optional `enabled` columns; extra columns are ignored. Alias and canonical values
are trimmed and case-folded. A row is valid only when `alias` is nonblank, `enabled` is absent or
`true` case-insensitively, and `canonical` resolves to one of `MASSAGE`, `FACIAL`, or `SAUNA`. The
first valid row for a normalized alias is authoritative; later duplicate alias rows do not override
it. Invalid rows must not crash the reconciler and must not make an alias eligible.

Normalize both
appointment and refund `service_area` values through the runtime alias map before matching. The
canonical service names `MASSAGE`, `FACIAL`, and `SAUNA` remain valid even if no alias row names
them. Alias matching is case-insensitive and trimmed, including padded alias tokens such as ` MSG `.
Matched report rows must emit the canonical uppercase service area, never the raw alias or raw
refund spelling; unmatched rows still leave `service_area` blank. Do not hardcode aliases that are
absent from the runtime alias file.
