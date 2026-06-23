# Record Layouts

Bills use `trip_id,rider_id,route_id,amount_cents,status,mode`.

Refunds use `trip_id,rider_id,route_id,amount_cents,mode`.

When dated matching is enabled, append `trip_date` as the last column on bills and `rebate_date` as the last column on refunds.

`/app/config/cutoff_calendar.txt` lists one date per line as `YYYY-MM-DD open` or `YYYY-MM-DD closed`.
