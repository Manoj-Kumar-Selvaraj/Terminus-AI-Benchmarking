# Rollup Matching

## Roll contract

An accumulator line is `ROLLED` when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `line_id` | Directive line identifier |
| `stream_id` | Input stream / feed id |
| `value_cents` | Numeric contribution in cents |
| `base_radix` | Radix encoding label |
| `segment_id` | Rollup segment for downstream totals |

Directive rows participate only when `state` equals `ELIGIBLE_STATE`. Accumulator rows participate only when `opcode` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

Each directive row may roll at most one accumulator line. Tie-break on latest `ingest_ts`, then earliest directive row.

## Segment aliases (milestone 2+)

`ALIAS_*` entries normalize abbreviated radix/segment codes before comparison. Reported `segment_id` on `ROLLED` rows is canonical from the consumed directive.

## Rollup windows (milestone 3)

Directive `ingest_ts` and accumulator `rollup_ts` must both fall inside the same open window for the line's `stream_id`.
