# Trailer Matching

## Balance contract

A claim is `BALANCED` when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `batch_id` | Store batch identifier |
| `account_no` | Settlement account |
| `net_cents` | Trailer net amount in cents |
| `dc_flag` | Debit/credit indicator |
| `branch_id` | Store branch code |

Batch rows participate only when `state` equals `ELIGIBLE_STATE`. Claim rows participate only when `reason_code` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

Each batch row may balance at most one claim. Tie-break on latest `posted_ts`, then earliest batch row.

## Debit/credit aliases (milestone 2+)

`ALIAS_*` entries normalize shorthand flags (`D`, `C`, `X`) before comparison. Reported `dc_flag` on `BALANCED` rows is canonical from the consumed batch.

## Settlement windows (milestone 3)

Batch `posted_ts` and claim `claim_ts` must both fall inside the same open window for the claim's `account_no`.
