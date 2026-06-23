# Replay Recovery Contract

The replay stage reads `/app/spool/downlink_segments/` and committed state under `/app/state/`.
Complete segment rows use:

`pass_id|segment_id|station_id|craft_id|channel|vcid|seq|frame_id|recv_ts|payload_hash|crc_status|segment_status`

Comment lines beginning with `#` are ignored. Complete rows require `crc_status=OK` and `segment_status=COMPLETE`.
`*.partial` records are unsafe input and must be reported in `/app/out/quarantine.psv`.

`/app/state/audit_ledger.psv` schema:

`pass_id|craft_id|channel|vcid|seq|frame_id|recv_ts|payload_hash|status`

Existing committed rows are preserved unchanged. Newly committed rows store `craft_id` and `channel` in their canonical rule-deck forms.

`/app/state/downlink_checkpoint.psv` schema:

`pass_id|craft_id|channel|vcid|last_seq|last_frame_id|checkpoint_ts`

`/app/out/replay_recovery_report.txt` must contain:

```
segments_seen=<integer>
frames_seen=<integer>
frames_committed=<integer>
duplicates_suppressed=<integer>
frames_quarantined=<integer>
checkpoint_status=<OK|STALE|MISSING|AHEAD_OF_LEDGER>
```

`/app/out/quarantine.psv` schema:

`source_file|line_no|pass_id|craft_id|channel|vcid|seq|frame_id|reason`
