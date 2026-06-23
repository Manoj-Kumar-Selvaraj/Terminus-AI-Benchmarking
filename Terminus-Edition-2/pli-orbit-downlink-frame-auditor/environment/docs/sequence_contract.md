# Sequence Continuity Contract

`/app/config/sequence_contract.psv` schema:

`craft_id|channel|vcid|min_seq|max_seq|wrap_enabled`

A sequence stream is identified by `pass_id + canonical craft_id + canonical channel + vcid`.
Sequences are zero-padded numeric values. `wrap_enabled` is `Y` or `N`.

`/app/out/downlink_anomalies.psv` schema:

`pass_id|craft_id|channel|vcid|seq|frame_id|reason|detail`

Allowed reasons:

- `SEQ_GAP`
- `DUPLICATE_SEQ`
- `OUT_OF_RANGE_SEQ`
- `BAD_SEQ_FORMAT`
- `UNEXPECTED_WRAP`

Every `SEQ_GAP` detail is exactly:

`missing_after=<previous-seq> before=<next-seq>`

Both endpoint values retain the configured sequence width. Multiple missing values between the same endpoints use the same detail.
