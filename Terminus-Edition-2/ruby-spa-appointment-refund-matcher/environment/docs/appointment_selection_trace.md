# Appointment selection trace

When dated refund batches are active, reconciliation writes
`/app/out/appointment_selection.csv` alongside the public report and summary.

Schema:

```text
refund_row,appointment_row,service_date
```

Rows appear in matched refund order. `refund_row` and `appointment_row` are zero-based physical
data-row positions and do not count CSV headers. `service_date` is copied from the selected
appointment row. Unmatched refunds are omitted.

When neither feed includes date columns, the reconciler writes the header row only with no data
lines. The trace is diagnostic output and does not replace the public refund report schema.
