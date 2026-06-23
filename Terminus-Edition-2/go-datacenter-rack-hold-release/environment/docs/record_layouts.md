# Record Layouts

Inputs use CSV rows keyed by full `hold_id`, `asset_id`, `aisle_id`, `rack`, and canonical `amount`.

## Holds (`/app/data/holds.csv`)

Columns: `hold_id,asset_id,aisle_id,access_tier,amount,hold_ts,status,rack`

## Releases (`/app/data/releases.csv`)

Columns: `release_id,hold_id,asset_id,aisle_id,access_tier,amount,release_ts,reason,rack`

## Access tier aliases (`/app/config/access_tier_aliases.csv`)

Columns: `alias,canonical`. Trim and case-fold both columns. Canonical targets must be `HOT`, `WARM`, or `COLD`.

## Realtime windows (`/app/config/windows.csv`)

Columns: `aisle_id,open_ts,close_ts,state`. Only `OPEN` windows are eligible; state matching is case-insensitive.

## Amount validation

Valid amounts are canonical positive integer strings from `1` through `999999999` with no leading zeros. Values such as `0`, `010`, `0104`, `+100`, decimals, blanks, and non-numeric text are invalid.

## Outputs

- Report: `/app/out/rack_release_report.csv` — `release_id,hold_id,asset_id,aisle_id,access_tier,amount,reason,status`
- Summary: `/app/out/rack_release_summary.txt` — `matched_count`, `matched_amount`, `unmatched_count`, `unmatched_amount`
- Rejections (milestone 3+): `/app/out/rack_release_rejections.csv` — `release_id,code`
- Audit (milestone 4): `/app/out/rack_release_audit.csv` — `aisle_id,total_releases,matched_count,unmatched_count,matched_amount,unmatched_amount`
