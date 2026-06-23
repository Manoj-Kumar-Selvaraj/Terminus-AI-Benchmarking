The pass-aware downlink auditor is now used during ground-station replay after receiver failover. Operators report duplicate committed frames and unsafe spool records in the same run. Preserve the existing static and pass-aware behavior, then add replay recovery using the committed ledger and checkpoint files.

The command remains:

```bash
/app/scripts/run_batch.sh
```

The evidence files include antenna, AGC, compressor, and dashboard messages. Those may be unrelated. The required behavior is defined by the contracts below.

## Existing formats

The existing catalog, audit, report, summary, consumption-trace, and pass-window formats remain unchanged.

## New input directory

Replay input is under:

```text
/app/spool/downlink_segments/
```

Files may use these extensions:

```text
*.seg
*.replay
*.partial
```

Comment lines beginning with `#` must be ignored. Complete replay frame rows use this pipe-delimited format:

```text
pass_id|segment_id|station_id|craft_id|channel|vcid|seq|frame_id|recv_ts|payload_hash|crc_status|segment_status
```

`crc_status` must be `OK` and `segment_status` must be `COMPLETE` for a replay row to be eligible for commit.

## New state formats

`/app/state/audit_ledger.psv` is pipe-delimited with this header:

```text
pass_id|craft_id|channel|vcid|seq|frame_id|recv_ts|payload_hash|status
```

Committed rows use `status=COMMITTED`.

`/app/state/downlink_checkpoint.psv` is pipe-delimited with this header:

```text
pass_id|craft_id|channel|vcid|last_seq|last_frame_id|checkpoint_ts
```

The checkpoint may be missing, stale, or ahead of the committed ledger.

## New output formats

`/app/out/replay_recovery_report.txt` must contain exactly these six key-value lines:

```text
segments_seen=<integer>
frames_seen=<integer>
frames_committed=<integer>
duplicates_suppressed=<integer>
frames_quarantined=<integer>
checkpoint_status=<OK|STALE|MISSING|AHEAD_OF_LEDGER>
```

`/app/out/quarantine.psv` must be pipe-delimited with this exact header:

```text
source_file|line_no|pass_id|craft_id|channel|vcid|seq|frame_id|reason
```

Allowed quarantine reasons for this recovery are:

```text
PARTIAL_SEGMENT
BAD_CRC
INCOMPLETE_SEGMENT
MALFORMED_FRAME
STALE_REPLAY
PASS_CLOSED
```

## Requirements

1. Preserve every existing static-audit and pass-window requirement.
2. Read complete downlink segment files from `/app/spool/downlink_segments/`.
3. Ignore comment lines beginning with `#`.
4. Treat `.partial` files as unsafe input.
5. Quarantine records from `.partial` files as `PARTIAL_SEGMENT`.
6. Quarantine malformed segment rows as `MALFORMED_FRAME`.
7. Quarantine rows where `crc_status` is not `OK` as `BAD_CRC`.
8. Quarantine rows where `segment_status` is not `COMPLETE` as `INCOMPLETE_SEGMENT`.
9. Validate replayed frames against pass-window eligibility.
10. Validate replayed frame craft/channel fields using runtime aliases.
11. Use `/app/state/audit_ledger.psv` as committed-state evidence.
12. Use `/app/state/downlink_checkpoint.psv` as restart-state evidence.
13. Tolerate a missing checkpoint.
14. Tolerate a stale checkpoint.
15. Tolerate a checkpoint ahead of the committed ledger.
16. Suppress replay duplicates already committed in the ledger.
17. Suppress duplicate replay rows that appear multiple times in the same run.
18. Never emit duplicate committed ledger rows for the same semantic frame.
19. Preserve existing committed ledger rows.
20. Append newly committed frames without changing the ledger schema.
21. Store newly committed `craft_id` and `channel` values in their canonical rule-deck forms.
22. Preserve existing committed ledger rows byte-for-field; canonical persistence applies only to newly committed rows.
23. Produce `/app/out/replay_recovery_report.txt` using the documented schema.
24. Produce `/app/out/quarantine.psv` using the documented schema.
25. Keep the static audit report, summary, and consumption trace compatible.
26. Continue processing later valid records after quarantining a bad record.
27. Do not accept a frame solely because it appears after a checkpoint.
28. Do not reject a valid frame solely because the checkpoint is stale.

## Verifier coverage stated as requirements

The verifier will check all of these externally visible behaviors: complete valid replay commit, ledger duplicate suppression, same-run duplicate suppression, stale checkpoint safety, missing checkpoint tolerance, ahead-of-ledger checkpoint safety, `.partial` quarantine, bad CRC quarantine, incomplete segment quarantine, malformed row quarantine, pass-closed quarantine, aliasing on replay rows, preservation of existing ledger rows, documented ledger schema for new rows, all required recovery report keys, recovery report count consistency, continued processing after bad rows, unchanged audit report compatibility, and unchanged audit summary compatibility.

Do not solve replay recovery by deleting state files, changing output schemas, or ignoring committed ledger evidence.
