# Record Layouts

Inputs use CSV rows keyed by full `event_id`, `account_id`, `reservation_id`, `region`, `sku_type`, and `amount` fields. Matching code should compare identifiers as whole values, not prefixes.

`sku_policy.csv` can be used by later run modes to describe region-specific sku_type eligibility with columns `region,sku_type,enabled,min_amount,max_amount,priority`. Region `*` is the fallback row when no exact region policy exists.
