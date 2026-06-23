# Compare Semantics

## Match contract

A check `EQUAL`s an expected row when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `field_id` | Stable field identifier in the schema registry |
| `schema_id` | Owning schema / contract version |
| `payload_hash` | Fingerprint of canonical serialized payload |
| `tolerance_key` | Numeric tolerance profile label |
| `segment_id` | Routing segment for downstream consumers |

Expected rows participate only when `state` equals `ELIGIBLE_STATE`. Actual rows participate only when `mode_code` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

## Consumption and tie-break

Each expected row may back at most one `EQUAL` result. When several expected rows qualify, pick the latest `recv_ts`, then the earliest row in `/app/data/expected.psv`.

## Alias normalization (milestone 2+)

`ALIAS_1` … `ALIAS_3` in `/app/src/semantic_rules.pli` use `raw=>canonical` pairs. Aliases apply case-insensitively during key comparison. Reported `segment_id` on `EQUAL` rows is the canonical value from the winning expected row.

## Schema windows (milestone 3)

When window mode is enabled, both expected `recv_ts` and actual `check_ts` must lie inside the same open window row in `/app/config/compare_windows.psv` for the check's `schema_id`. Window rows must carry `state` equal to `OPEN_COMPARE_STATE`.

## Status vocabulary

- `EQUAL` — all gates passed and a unique expected row was consumed
- `DIFFER` — no qualifying expected row; `segment_id` in the report is blank
