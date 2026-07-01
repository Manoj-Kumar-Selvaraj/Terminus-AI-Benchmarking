# Jenkins home recovery runbook

Preserve the live Jenkins home until a complete compatible backup has been validated and staged. A backup directory is not trustworthy just because it exists, and recovery must not copy a hardcoded snapshot name.

A candidate snapshot is valid only when all of these checks pass:

- `manifest.json` parses successfully.
- The manifest is compatible with the selected target Jenkins version.
- Every declared required file exists.
- Every declared required file matches its checksum.
- All XML files parse successfully.
- `jobs.json` contains unique, non-empty logical job names.
- Every inventory job has a parseable config file.

Choose the newest valid compatible snapshot by `created_at`. Newer corrupt or incompatible candidates may be present and must be skipped. `plan --json` must expose the selected snapshot as top-level string `selected_snapshot` without mutating state.

If no complete compatible snapshot exists, fail before creating any `recovery_state` directory with stderr containing `no complete compatible backup`.

Stage the selected snapshot under `recovery_state/staging` before modifying the live home. A fault after staging must not expose staged files as live state. Preserve unrelated live-home files, additional valid jobs, unknown controller-state fields, audit fields, and provenance metadata. When restoring `jobs.json`, merge the selected backup's valid job entries with existing live-home valid job entries; do not replace the live `jobs.json` wholesale or drop additional live jobs that are not present in the backup.

During activation, apply only the selected XML files, inventory, and job configs from the staged snapshot. Remove only the failed upgrade lock. Do not delete unrelated live-home data.

The restored controller state must set:

- `home_schema`: `recovered-target`
- `upgrade_status`: `RESTORED`
- `restored_from_snapshot`: selected snapshot ID
- `previous_version`: selected snapshot source version

Unrelated controller-state fields must be preserved.

The `after_home_stage` fault point exits non-zero after durable staging while leaving live home unchanged. Resuming with the same owner must reuse the durable stage and produce exactly one `home_staged` event and exactly one `home_committed` event. A different owner remains fenced.
