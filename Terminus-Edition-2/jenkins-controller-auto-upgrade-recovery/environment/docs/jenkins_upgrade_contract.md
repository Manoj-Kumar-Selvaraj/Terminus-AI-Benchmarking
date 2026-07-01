# Offline Jenkins upgrade contract

This task models a Jenkins controller upgrade incident without a live Jenkins or Kubernetes cluster. The selected target is authoritative; recovery must not downgrade it just to make the controller boot.

The implementation surface is `/app/recovery/main.go`, invoked through `/app/scripts/jenkins-recover`. Tests may run the same implementation against copied or modified incident roots by setting `APP_ROOT`; default `APP_ROOT` is `/app`.

Stable public identity comes from `cluster/controller_deployment.json`, including cluster, namespace, deployment, service, home claim, and home path. Compatibility values are data, not constants. Read target and runtime compatibility from `config/version_contract.json`, plugin candidates from `config/plugin_catalog.json`, and backup compatibility from backup manifests.

## Runtime recovery

Read the selected Jenkins target from `cluster/controller_deployment.json` and resolve runtime requirements from `config/version_contract.json`. If the selected target is absent from the version contract, fail before mutation with stderr containing `absent from version contract`.

Runtime changes must be atomic. Update only runtime compatibility fields such as Java/runtime image values, and preserve deployment identity plus unknown fields. The `operation_id` must be deterministic from deployment identity and selected target, and it must change if either deployment identity or selected target changes.

`plan --json` is read-only and returns `operation_id` plus an `actions` array. The runtime action must include dynamically derived `target_version` and `required_java`.

## Upgrade policy recovery

Recovered upgrade automation must be pinned instead of continuing unattended movement. Policy recovery must preserve `audit`, `change_ticket`, `source_version`, `last_upgrade_id`, nested audit fields, provenance metadata, and unknown future fields.

Before policy mutation, recovery must complete the cumulative plan checks for the requested scope. Policy recovery records `preflight_completed` before `policy_committed`.

The recovered policy must set exactly these safety fields:

- `auto_upgrade_enabled`: `false`
- `channel`: `pinned-lts`
- `pin_target_version`: `true`
- `target_version`: selected controller target from the deployment
- `java_preflight_required`: `true`
- `backup_required`: `true`
- `required_backup_snapshot`: the snapshot selected by validated home recovery
- `abort_on_failed_preflight`: `true`
- `lock_strategy`: `clear-after-verified-restore`

`plan --json` for policy recovery must include `guards` as an array of plain strings covering Java preflight, verified backup, and owner lease decisions. Do not emit structured guard objects.