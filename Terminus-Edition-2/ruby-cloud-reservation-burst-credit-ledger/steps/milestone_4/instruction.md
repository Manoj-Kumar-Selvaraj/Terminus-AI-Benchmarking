Add region-specific SKU policy enforcement from `/app/config/sku_policy.csv`, whose columns are `region,sku_type,enabled,min_amount,max_amount,priority`. Preserve every existing identity, status, reason, timestamp, window, alias, source-consumption, ordering, and output rule.

A source row is policy-eligible only when an enabled policy row covers its canonical `sku_type` and its integer amount falls within the inclusive `min_amount` and `max_amount` range. Normalize policy `sku_type` fields with the existing aliases. Trim and case-fold policy `region` values before matching source and correction regions. Treat `true`, `yes`, `y`, `1`, and `enabled` as enabled case-insensitively. Ignore policy rows whose `min_amount`, `max_amount`, or `priority` is not numeric.

Exact-region policy rows override wildcard `*` rows for the same SKU type. Do not fall back to wildcard rows when exact-region rows exist but none are enabled and in range.

Correction `sku_type` value `ANY`, after trimming and case folding, may match any policy-allowed canonical source `sku_type` that passes every other gate. Named correction SKU types and aliases require exact canonical source equality. Unknown source types remain ineligible even if a policy row names them.

When several unused sources qualify, choose the latest `reserve_ts`, then the highest applicable policy `priority`, then the earliest source input row. Matched rows emit the selected source's canonical `sku_type`, never `ANY`. Report schemas, correction order, status labels, blank unmatched `sku_type`, and positive integer summary totals stay unchanged.
