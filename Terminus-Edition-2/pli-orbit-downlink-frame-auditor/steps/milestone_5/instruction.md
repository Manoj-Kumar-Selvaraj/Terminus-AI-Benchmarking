The same orbital pass may be observed by more than one ground station during handoff. The auditor must now validate station authority and structured segment integrity while preserving all earlier outputs. Operators have included compressor and antenna warnings in the evidence, but the acceptance contract is the station and segment behavior below.

The command remains:

```bash
/app/scripts/run_batch.sh
```

## Existing formats

All existing static-audit, pass-window, replay, continuity, state, and output formats remain unchanged.

## New station priority input format

`/app/config/station_priority.psv` is pipe-delimited with this header:

```text
pass_id|craft_id|channel|station_id|priority|handoff_open_ts|handoff_close_ts
```

Lower numeric `priority` means more authoritative. Station authority is valid only when:

```text
handoff_open_ts <= recv_ts <= handoff_close_ts
```

Craft and channel fields must be evaluated after rule-deck aliasing.

## Structured segment input format

M5 segment files may contain structured rows.

Header row:

```text
HDR|pass_id|segment_id|station_id|craft_id|channel|opened_ts
```

Frame row:

```text
FRM|pass_id|segment_id|station_id|craft_id|channel|vcid|seq|frame_id|recv_ts|payload_hash|crc_status|segment_status
```

Trailer row:

```text
TRL|pass_id|segment_id|station_id|frame_count|hash_total|closed_ts
```

The `hash_total` control total is the decimal sum of all ASCII byte values from each valid `FRM` row's `payload_hash` in that segment.

## New output format

`/app/out/station_conflicts.psv` must be pipe-delimited with this exact header:

```text
pass_id|craft_id|channel|vcid|seq|frame_id|station_id|reason|detail
```

Allowed reasons are:

```text
PAYLOAD_CONFLICT
LOWER_PRIORITY_DUPLICATE
STATION_OUTSIDE_HANDOFF
SEGMENT_COUNT_MISMATCH
SEGMENT_HASH_MISMATCH
MISSING_HEADER
MISSING_TRAILER
SEGMENT_ID_MISMATCH
FRAME_AFTER_TRAILER
```

## Requirements

1. Preserve every existing static-audit, pass-window, replay-recovery, and continuity requirement.
2. Read `/app/config/station_priority.psv`.
3. Apply canonical craft/channel values before station-priority lookup.
4. Treat lower numeric `priority` as more authoritative.
5. Validate station authority with `handoff_open_ts <= recv_ts <= handoff_close_ts`.
6. Emit `STATION_OUTSIDE_HANDOFF` when a station receives a frame outside its authority window.
7. Compare duplicate frames across stations by `pass_id + craft_id + channel + vcid + seq`.
8. Treat same stream and sequence with the same payload hash as a duplicate station observation.
9. Prefer the highest-priority eligible station copy.
10. Emit `LOWER_PRIORITY_DUPLICATE` for non-authoritative duplicate station observations.
11. Emit `PAYLOAD_CONFLICT` when the same stream and sequence has different payload hashes across station observations.
12. Never silently commit two conflicting payloads for the same stream sequence.
13. Support segment files with `HDR`, `FRM`, and `TRL` rows.
14. Require each structured segment to have exactly one matching header.
15. Require each structured segment to have exactly one matching trailer.
16. Emit `MISSING_HEADER` for frame groups without a matching header.
17. Emit `MISSING_TRAILER` for frame groups without a matching trailer.
18. Emit `SEGMENT_ID_MISMATCH` when header, frame, and trailer segment identifiers disagree.
19. Emit `SEGMENT_COUNT_MISMATCH` when trailer `frame_count` does not equal the number of valid `FRM` rows in the segment.
20. Emit `SEGMENT_HASH_MISMATCH` when trailer `hash_total` does not match the segment control-total contract.
21. Emit `FRAME_AFTER_TRAILER` when frame rows appear after a trailer row for the same segment.
22. Continue processing other valid segments after a segment integrity failure.
23. Exclude invalid segment frames from committed ledger output.
24. Include station and segment findings in `/app/out/station_conflicts.psv`.
25. Keep `/app/out/downlink_anomalies.psv` compatible.
26. Keep `/app/out/replay_recovery_report.txt` compatible.
27. Keep `/app/out/quarantine.psv` compatible.
28. Keep `/app/out/audit_report.csv` and `/app/out/audit_summary.txt` compatible.
29. Do not treat station conflict suppression as replay duplicate suppression.
30. Do not treat replay duplicate suppression as station conflict resolution.

## Verifier coverage stated as requirements

The verifier will check all of these externally visible behaviors: highest-priority eligible station selection, lower-priority duplicate reporting, payload conflict reporting, conflict rows not both committed, station-before-handoff reporting, station-after-handoff reporting, aliasing before station lookup, missing header reporting, missing trailer reporting, header/frame segment mismatch reporting, frame/trailer segment mismatch reporting, trailer count mismatch reporting, trailer hash-total mismatch reporting, frame-after-trailer reporting, invalid segment frames excluded from the ledger, later valid segments still processed, required station conflict header, expected station conflict reason values, valid sequence anomaly output, valid replay recovery output, valid quarantine output, valid static audit report, and valid static audit summary.

Do not satisfy this recovery by deleting alternate station observations, changing the ledger schema, or suppressing station findings as generic replay duplicates.
