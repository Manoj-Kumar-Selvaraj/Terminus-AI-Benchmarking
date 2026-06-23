Replay recovery is now required to preserve downlink continuity information. Operations need the auditor to report missing, duplicated, malformed, out-of-range, and unexpected wrap sequence behavior without regressing static audit or replay recovery outputs.

The command remains:

```bash
/app/scripts/run_batch.sh
```

## Existing formats

All existing static-audit, pass-window, replay, state, and output formats remain unchanged.

## New input format

`/app/config/sequence_contract.psv` is pipe-delimited with this header:

```text
craft_id|channel|vcid|min_seq|max_seq|wrap_enabled
```

`wrap_enabled` is `Y` or `N`. Craft and channel values are canonical values after applying rule-deck aliases.

A sequence stream is identified by:

```text
pass_id + craft_id + channel + vcid
```

## New output format

`/app/out/downlink_anomalies.psv` must be pipe-delimited with this exact header:

```text
pass_id|craft_id|channel|vcid|seq|frame_id|reason|detail
```

Allowed reasons are:

```text
SEQ_GAP
DUPLICATE_SEQ
OUT_OF_RANGE_SEQ
BAD_SEQ_FORMAT
UNEXPECTED_WRAP
```

## Requirements

1. Preserve every existing static-audit, pass-window, and replay-recovery requirement.
2. Read `/app/config/sequence_contract.psv`.
3. Apply craft and channel aliases before sequence contract lookup.
4. Evaluate sequence continuity independently per stream.
5. Treat `seq` as a zero-padded numeric sequence.
6. Reject malformed sequence values from continuity calculations.
7. Emit `BAD_SEQ_FORMAT` for malformed sequence values.
8. Emit `OUT_OF_RANGE_SEQ` for sequence values outside configured `min_seq` and `max_seq`.
9. Emit `SEQ_GAP` for every missing sequence value between committed frames in a stream.
10. Set every `SEQ_GAP` detail exactly to `missing_after=<previous-seq> before=<next-seq>`, preserving the configured zero-padding. Multiple missing values between the same endpoints use the same detail.
11. Emit `DUPLICATE_SEQ` when two different frames claim the same sequence in the same stream.
12. Suppress replay duplicates without falsely reporting `DUPLICATE_SEQ`.
13. Treat out-of-order arrival as valid when sequence continuity is complete.
14. Detect gaps after evaluating stream sequence values, not raw file order.
15. Honor wrap behavior when `wrap_enabled=Y`.
16. Emit `UNEXPECTED_WRAP` when wrap occurs and `wrap_enabled=N`.
17. Do not mix sequence state across craft IDs.
18. Do not mix sequence state across channels.
19. Do not mix sequence state across VCIDs.
20. Do not mix sequence state across pass IDs.
21. Preserve `/app/out/downlink_anomalies.psv` schema.
22. Keep replay recovery outputs compatible.
23. Keep static audit outputs compatible.

## Verifier coverage stated as requirements

The verifier will check all of these externally visible behaviors: clean contiguous sequence without false gaps, single missing sequence gap, multiple missing sequence values, out-of-order complete sequence without false gaps, duplicate replay suppression not becoming duplicate sequence anomalies, different-frame duplicate sequence detection, malformed sequence anomaly, out-of-range sequence anomaly, configured wrap acceptance, unexpected wrap anomaly, no state bleed across craft IDs, no state bleed across channels, no state bleed across VCIDs, no state bleed across pass IDs, aliasing before sequence contract lookup, required anomaly header, populated gap detail, valid replay recovery output, and valid audit output.

Do not report sequence anomalies by changing the replay ledger schema or the static audit report schema.
