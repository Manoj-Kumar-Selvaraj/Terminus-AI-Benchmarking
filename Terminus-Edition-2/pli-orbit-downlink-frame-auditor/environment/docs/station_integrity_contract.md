# Station Handoff and Segment Integrity Contract

`/app/config/station_priority.psv` schema:

`pass_id|craft_id|channel|station_id|priority|handoff_open_ts|handoff_close_ts`

Lower numeric `priority` is more authoritative. Station authority is valid only when
`handoff_open_ts <= recv_ts <= handoff_close_ts`.

Structured downlink segment files may contain:

Header:

`HDR|pass_id|segment_id|station_id|craft_id|channel|opened_ts`

Frame:

`FRM|pass_id|segment_id|station_id|craft_id|channel|vcid|seq|frame_id|recv_ts|payload_hash|crc_status|segment_status`

Trailer:

`TRL|pass_id|segment_id|station_id|frame_count|hash_total|closed_ts`

The `hash_total` fixture control total is the decimal sum of all ASCII byte values from each valid `FRM` row's `payload_hash` in that segment.

`/app/out/station_conflicts.psv` schema:

`pass_id|craft_id|channel|vcid|seq|frame_id|station_id|reason|detail`

Allowed reasons:

- `PAYLOAD_CONFLICT`
- `LOWER_PRIORITY_DUPLICATE`
- `STATION_OUTSIDE_HANDOFF`
- `SEGMENT_COUNT_MISMATCH`
- `SEGMENT_HASH_MISMATCH`
- `MISSING_HEADER`
- `MISSING_TRAILER`
- `SEGMENT_ID_MISMATCH`
- `FRAME_AFTER_TRAILER`
