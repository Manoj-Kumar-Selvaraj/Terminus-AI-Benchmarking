# Manifest Matching

## Consistency contract

A check is `CONSISTENT` when all five compare keys agree after optional alias normalization:

| Key | Role |
|-----|------|
| `workload_id` | Deployment / StatefulSet identifier |
| `namespace` | Kubernetes namespace |
| `selector_label` | Pod selector revision label (summed in totals) |
| `port_name` | Declared container port name |
| `probe_path` | HTTP probe path registered on the manifest |

Manifest rows participate only when `state` equals `ELIGIBLE_STATE`. Check rows participate only when `check_code` is listed in `REASON_1`, `REASON_2`, or `REASON_3`.

## Consumption and tie-break

Each manifest row may satisfy at most one check. When several manifest rows qualify, pick the latest `applied_ts`, then the earliest row in `/app/data/manifests.psv`.

## Port aliases (milestone 2+)

`ALIAS_*` entries normalize shorthand port names (`8080`, `http`) to canonical service port names before comparison. Reported `port_name` on `CONSISTENT` rows is canonical from the consumed manifest.

## Rollout windows (milestone 3)

When window mode is enabled, manifest `applied_ts` and check `check_ts` must both fall inside the same open window for the check's `namespace`.
