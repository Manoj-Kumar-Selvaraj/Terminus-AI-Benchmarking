Extend `/app/scripts/reconcile.sh` with payer clearance caps from `/app/config/payer_clearance_caps.csv`. The file has header `payer,cap_cents` and lists one cumulative clearance limit per canonical payer (`CARD`, `CASH`, `INSURANCE`). Payers omitted from the file are uncapped.

Process credits in input order. After a credit passes every milestone 1–3 gate and a sample row is selected, apply the cap gate before consuming the sample:

1. Resolve the credit payer to its canonical value (milestone 2 aliases still apply).
2. If that payer has a cap, the running cleared total for that payer plus this credit's `amount_cents` must be **less than or equal to** the cap.
3. If the cap would be exceeded, emit `UNMATCHED` for that credit and **do not** consume the sample row or increase the payer's running total.
4. On a successful `MATCHED` credit, add the credit amount to that payer's running total.

Running totals are per canonical payer and accumulate only from matched credits, in credit-file order. Undated inputs still use milestone 2 matching; dated inputs still use milestone 3 calendar rules. Caps apply in both modes when the caps file is present.

Worked example: caps `CARD,10000` and `CASH,20000`. Credits in order: `5500 CARD` (matches), `5000 CARD` (would reach 10500 > 10000 → `UNMATCHED`, sample stays available), `4400 CASH` (matches, CASH total 4400). The blocked CARD credit does not consume its sample; a later eligible credit could still match that sample if caps allow.

Keep report and summary schemas unchanged.
