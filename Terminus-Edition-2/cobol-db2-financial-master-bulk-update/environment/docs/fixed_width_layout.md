# FINUPD fixed-width layout

All input records are newline-delimited fixed-block text.

Header record:

```text
H batch-id(10) business-date(8) source(8)
```

Detail record:

```text
D sequence(6) account-id(12) op-code(3) sign(1) amount-cents(12) group-id(6) event-id(8)
```

Supported op-codes:

- `BAL`: add signed cents to `master.balance_cents` and write a ledger side effect.
- `RAT`: set `master.rate_bp` from the unsigned amount field.
- `HLD`: set hold flag to `Y` for non-zero amount, otherwise `N`.
- `LIM`: set credit limit in both `master.credit_limit_cents` and `risk.exposure_limit_cents` atomically.

Trailer record:

```text
T batch-id(10) detail-count(6) financial-total-sign(1) financial-total-cents(12)
```

The trailer financial total covers only `BAL` detail amounts. Before any mutation, the batch must fail closed if header/trailer batch IDs differ, detail count mismatches, sequence/account/op fields are malformed, or the BAL total does not equal the trailer.

Reject output records under `/app/out` use:

```text
R sequence(6) account-id(12) sqlcode(+/-NNNN) reason(32)
```
