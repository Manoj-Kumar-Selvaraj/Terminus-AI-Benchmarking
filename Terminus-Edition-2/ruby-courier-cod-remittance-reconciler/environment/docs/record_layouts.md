# Record Layouts

## Deliveries (`/app/data/deliveries.csv`)

Columns: `parcel_id,courier_id,station_id,kind,amount,source_ts,status,location`

## Remittances (`/app/data/remittances.csv`)

Columns: `action_id,parcel_id,courier_id,station_id,kind,amount,action_ts,reason,location`

## Station windows (`/app/config/windows.csv`)

Columns: `station_id,open_ts,close_ts,state`. Only `OPEN` windows are eligible.

## Milestone 1 matching

Exact match on `parcel_id`, `courier_id`, `station_id`, `location`, and `amount`. Delivery status must be `DELIVERED`. Correction reasons must be `RETURN`, `SHORT`, or `ADJUST`. Canonical kinds are `CASH`, `UPI`, and `CARD`. Timestamps must be 14-digit numeric values; `action_ts` must be on or after `source_ts`. The delivery timestamp must fall inside an `OPEN` window for the same `station_id`, and the correction timestamp must not exceed that window close. Each delivery row is consumed once. When multiple unused deliveries qualify, choose the latest `source_ts`; if timestamps tie, choose the earliest delivery input row.

## Milestone 2 aliases

After trim and case folding: `CSH` → `CASH`, `QR` → `UPI`, `CC` → `CARD`. Emit canonical kinds on matched rows.

## Outputs

- Report: `/app/out/cod_remittance_report.csv` — `action_id,parcel_id,courier_id,station_id,kind,amount,reason,status`
- Summary: `/app/out/cod_remittance_summary.txt` — `matched_count`, `matched_amount`, `unmatched_count`, `unmatched_amount`
