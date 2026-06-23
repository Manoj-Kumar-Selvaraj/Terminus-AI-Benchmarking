# Record Layouts

Orders use `order_id,seller_id,amount_cents,status,lane`.

Payouts use `order_id,seller_id,amount_cents,lane`.

When dated matching is enabled, append `ship_date` as the last column on orders and `payout_date` as the last column on payouts.

`/app/config/cutoff_calendar.txt` lists one date per line as `YYYY-MM-DD open` or `YYYY-MM-DD closed`.

`/app/config/methods.csv` lists canonical fulfillment lanes (`D2D`, `LOCKER`, `STORE`) with an `enabled` flag per row.

Legacy payout lane aliases `DRP`, `PKU`, and `RTL` map to `D2D`, `LOCKER`, and `STORE`.
