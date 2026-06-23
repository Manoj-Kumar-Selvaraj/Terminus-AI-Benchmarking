# Policy And Window Examples

`/app/config/windows.csv` is used starting in milestone 3. Only rows with state `OPEN` and numeric timestamps make a source event eligible.

`/app/config/resource_policy.csv` is used starting in milestone 4. Policy rows are keyed by station and canonical resource type. The `enabled` column is case-insensitive, while `priority` and `max_station_amount` must be numeric.
