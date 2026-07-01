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

For SQLCODE `+100` missing-master business rejects, write reason `MASTER_ROW_NOT_FOUND` padded or truncated to the 32-byte reason field.

## Downstream GL feed (milestone 6 close mode)

Close mode (`--close DATE`) emits `glfeed_<DATE>.dat` beneath `--out` as a newline-delimited fixed-block text feed when the chain verifies. The file holds one header, one detail per settled batch in chain order, and one trailer. When `chain_index[DATE]` is empty the file is created as an empty zero-byte file. When close fails with `CLOSE_BROKEN`, the file is created empty.

Header record (15 bytes plus newline):

```text
H business-date(8) batch-count(6)
```

Detail record (94 bytes plus newline), one per settled batch in chain order:

```text
G batch-id(10) chain-sha256(64) detail-count(6) financial-total-sign(1) financial-total-cents(12)
```

Trailer record (28 bytes plus newline):

```text
T business-date(8) batch-count(6) grand-total-sign(1) grand-total-cents(12)
```

The trailer grand total is the signed sum of the per-batch `financial_total` values in chain order. `batch_id` is left-justified and space-padded to 10 bytes. `chain_sha256` is the exact 64-character lowercase hex string from the matching `control_totals` entry. All integer fields are zero-padded; the sign characters are `+` or `-`.
