# Tape Matching

## Verification contract

An audit is `VERIFIED` when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `record_id` | Tape record identifier |
| `volume_id` | Mounted volume label |
| `length_hash` | Block length fingerprint (summed in totals) |
| `block_no` | Catalog block number |
| `reel_id` | Physical reel identifier |

Catalog rows participate only when `state` equals `ELIGIBLE_STATE`. Audit rows participate only when `verdict_code` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

Each catalog row may verify at most one audit. Tie-break on latest `recv_ts`, then earliest catalog row.

## Volume aliases (milestone 2+)

`ALIAS_*` entries normalize abbreviated volume and block labels before comparison. Reported `block_no` on `VERIFIED` rows is canonical from the consumed catalog row.

## Mount windows (milestone 3)

Catalog `recv_ts` and audit `audit_ts` must both fall inside the same open window for the audit's `volume_id`.
