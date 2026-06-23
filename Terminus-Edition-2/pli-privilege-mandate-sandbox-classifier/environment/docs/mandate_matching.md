# Mandate Matching

## Authorization contract

An audit is `AUTHORIZED` when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `mandate_id` | Signed privilege mandate identifier |
| `service_id` | Owning microservice |
| `cap_token` | Capability token weight used for summary totals |
| `payload_hash` | Hash of privileged operation payload |
| `sandbox_class` | Sandbox isolation tier |

Mandate rows participate only when `state` equals `ELIGIBLE_STATE`. Audit rows participate only when `verdict_code` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

## Consumption and tie-break

Each mandate row may authorize at most one audit. When several mandate rows qualify, pick the latest `recv_ts`, then the earliest row in `/app/data/mandates.psv`.

## Capability aliases (milestone 2+)

`ALIAS_*` entries normalize abbreviated sandbox class labels before comparison. Reported `sandbox_class` on `AUTHORIZED` rows is canonical from the consumed mandate.

## Sandbox windows (milestone 3)

When window mode is enabled, mandate `recv_ts` and audit `audit_ts` must both fall inside the same open window for the audit's `service_id`.
