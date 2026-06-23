# Record Layouts

Tours use `tour_id,passenger_id,amount_cents,status,cabin_tier`.

Deposits use `tour_id,passenger_id,amount_cents,cabin_tier`.

When dated matching is enabled, append `tour_date` as the last column on tours and `deposit_date` as the last column on deposits.

`/app/config/cutoff_calendar.txt` lists one date per line as `YYYY-MM-DD open` or `YYYY-MM-DD closed`.

Policy files: `fleet_policy.csv` (`cabin_tier,enabled,priority`), `passenger_limits.csv` (`passenger_id,effective_date,max_daily_amount_cents`), `weather_blackouts.csv` (`tour_id,start_date,end_date`).
