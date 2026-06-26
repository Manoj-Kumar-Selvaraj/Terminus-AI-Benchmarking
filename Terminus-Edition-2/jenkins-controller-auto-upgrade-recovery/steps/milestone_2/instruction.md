# M2 — Restore Jenkins home after failed upgrade boot

The runtime mismatch is no longer the first blocker, but Jenkins home was left in an unsafe partial-upgrade state. The controller home contains malformed XML, failed upgrade markers, and incomplete queue state from the abrupt boot failure.

Evidence is available in:

- `/app/evidence/home_integrity_probe.txt`
- `/app/docs/restore_runbook.md`
- `/app/backups/pre-upgrade-20260618/`
- `/app/jenkins_home/`


## Shared constraints

- Work under `/app`.
- Use `/app/scripts/run_controller.sh` or `python3 /app/scripts/jenkins_cluster_sim.py diagnose --json` to exercise the offline simulator.
- Do not require a real Jenkins controller, Kubernetes cluster, network access, Jenkins CLI, or cloud credentials.
- Preserve the cluster identity: `prod-ci-east`, namespace `jenkins-prod`, deployment `jenkins-controller`, service `jenkins-web`, and PVC claim `jenkins-home-rwo`.
- Preserve `/app/jenkins_home`; do not replace it with a tiny fake home or delete jobs/credentials.
- Preserve the target Jenkins version `2.462.3` from the incident contract.
- Do not edit tests or simulator output files as a substitute for restoring the simulated system state.


## Input format

Important home files include:

```text
/app/jenkins_home/config.xml
/app/jenkins_home/credentials.xml
/app/jenkins_home/queue.xml
/app/jenkins_home/controller_state.json
/app/jenkins_home/UPGRADE.lock
/app/jenkins_home/jobs/**/config.xml
```

Backup files are stored under:

```text
/app/backups/pre-upgrade-20260618/
```

`/app/jenkins_home/controller_state.json` must remain valid JSON. After a successful M2 restore it must record the recovered target home and the backup snapshot used. The verifier and simulator expect these exact keys and values:

```json
{
  "previous_version": "2.426.3",
  "target_version": "2.462.3",
  "home_schema": "recovered-target",
  "upgrade_status": "RESTORED",
  "restored_from_snapshot": "pre-upgrade-20260618"
}
```

- `previous_version` — Jenkins release before the failed auto-upgrade (`2.426.3`).
- `target_version` — incident target controller release (`2.462.3`); must match `config.xml` and the cluster contract.
- `home_schema` — recovered home marker required by the simulator (`recovered-target`, not `partial-upgrade`).
- `upgrade_status` — post-restore lifecycle marker (`RESTORED`, not `FAILED_BOOT`).
- `restored_from_snapshot` — backup directory name under `/app/backups/` (`pre-upgrade-20260618`).

Additional keys such as `last_successful_boot` may remain if already present, but the fields above are required.

## Expected result

After M2, diagnostics must no longer stop at phase `HOME_CORRUPT`. Later phases may still fail.

## Requirements tested in M2

1. Every M1 runtime compatibility requirement remains satisfied.
2. `config.xml`, `credentials.xml`, and `queue.xml` are valid XML.
3. `config.xml` records the target Jenkins version `2.462.3`.
4. Failed boot upgrade locks are not left active in live Jenkins home.
5. `controller_state.json` records `home_schema` `recovered-target`, `upgrade_status` `RESTORED`, `target_version` `2.462.3`, and `restored_from_snapshot` `pre-upgrade-20260618`.
6. Required jobs `payments-ledger/main`, `shared-library/test`, and `platform-smoke/healthcheck` remain present.
7. Required credential IDs from the backup are preserved.
8. The task does not pass by deleting the home directory or replacing it with a minimal fake config.
