# Plan Consumption Trace

Dated reconciliation writes `/app/out/plan_consumption.csv` with this schema:

```text
credit_row,plan_row,cycle_end
```

Rows appear in matched credit order. `credit_row` and `plan_row` are zero-based physical data-row positions and do not count CSV headers. `cycle_end` is copied from the selected plan row and is blank when dated processing is inactive. Unmatched credits are omitted.

The trace is diagnostic output. It does not replace or alter the public credit report or summary schemas.
