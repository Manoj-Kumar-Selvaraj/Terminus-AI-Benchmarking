# Runtime Input Fixtures

The verifier overwrites `/app/data/events.csv` and `/app/data/settlements.csv` at runtime. The shipped files are smoke-test fixtures for manual runs with `/app/scripts/run_batch.sh`.

`events.csv` source rows use `parcel_id,meter_id,station_id,resource_type,amount,event_ts,status,feeder`.

`settlements.csv` correction rows use `settlement_id,parcel_id,meter_id,station_id,resource_type,amount,settle_ts,reason,feeder`.
