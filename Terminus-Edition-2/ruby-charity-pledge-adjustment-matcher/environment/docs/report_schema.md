# Report schema

Outputs are defined in `/app/config/report_schema.json`.

## `adjustment_report.csv`

One row per adjustment input row, preserving input order:

```
pledge_id,donor_id,fund,amount_cents,status
```

`status` is `MATCHED` or `UNMATCHED`. `fund` is the canonical code when matched.

## `adjustment_summary.json`

```json
{
  "matched_count": 0,
  "matched_amount_cents": 0,
  "unmatched_count": 0,
  "unmatched_amount_cents": 0
}
```

All amount fields are non-negative integers.
