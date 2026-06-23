# Drift Matching

## Alignment contract

A scan is `ALIGNED` when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `resource_id` | Cloud resource identifier |
| `resource_group` | Owning resource group / stack |
| `attr_hash` | Attribute fingerprint used in summary totals |
| `module_name` | Declared infrastructure module |
| `region_code` | Deployment region |

Ideal rows participate only when `state` equals `ELIGIBLE_STATE`. Scan rows participate only when `scan_code` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

## Consumption and tie-break

Each ideal row may align at most one scan. When several ideal rows qualify, pick the latest `ideal_ts`, then the earliest row in `/app/data/ideal.psv`.

## Module aliases (milestone 2+)

`ALIAS_*` entries normalize abbreviated module and region labels before comparison. Reported `module_name` on `ALIGNED` rows is canonical from the consumed ideal row.

## Audit windows (milestone 3)

When window mode is enabled, ideal `ideal_ts` and scan `scan_ts` must both fall inside the same open window for the scan's `resource_group`.
