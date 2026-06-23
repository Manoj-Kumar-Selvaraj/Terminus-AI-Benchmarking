# Mainframe Tape Record Integrity Auditor

Tape operations compares block audits in `/app/data/tape_audits.psv` against the mount catalog in `/app/data/tape_catalog.psv`. Policy constants are DCL declarations in `/app/src/tape_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/tape_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Catalog** (`/app/data/tape_catalog.psv`): `record_id`, `volume_id`, `length_hash`, `block_no`, `reel_id`, `recv_ts`, `state`, `kind_code`.

**Audits** (`/app/data/tape_audits.psv`): `claim_id`, `record_id`, `volume_id`, `length_hash`, `block_no`, `audit_ts`, `verdict_code`, `reel_id`.

**Mount windows** (`/app/config/mount_windows.psv`, milestone 3): `volume_id`, `open_ts`, `close_ts`, `state`.

See `/app/docs/tape_matching.md`, `/app/docs/tape_alias_rules.md`, and `/app/docs/mount_window_rules.md`.

## Outputs

See `/app/docs/tape_report_schema.md` and `/app/docs/tape_summary_contract.md`.
