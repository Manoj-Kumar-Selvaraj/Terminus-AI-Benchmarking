# M4 — Make future auto-upgrades safe and auditable

The controller can now progress through plugin loading, but the same unguarded auto-upgrade controller could repeat the outage. The upgrade policy must prevent an incompatible unattended rollout and require preflight/backup evidence before future target changes.

Evidence is available in:

- `/app/evidence/upgrade_controller_audit.json`
- `/app/cluster/auto_upgrade_policy.json`
- `/app/backups/pre-upgrade-20260618/`


## Shared constraints

- Work under `/app`.
- Use `/app/scripts/run_controller.sh` or `python3 /app/scripts/jenkins_cluster_sim.py diagnose --json` to exercise the offline simulator.
- Do not require a real Jenkins controller, Kubernetes cluster, network access, Jenkins CLI, or cloud credentials.
- Preserve the cluster identity: `prod-ci-east`, namespace `jenkins-prod`, deployment `jenkins-controller`, service `jenkins-web`, and PVC claim `jenkins-home-rwo`.
- Preserve `/app/jenkins_home`; do not replace it with a tiny fake home or delete jobs/credentials.
- Preserve the target Jenkins version `2.462.3` from the incident contract.
- Do not edit tests or simulator output files as a substitute for restoring the simulated system state.


## Input format

`/app/cluster/auto_upgrade_policy.json` is JSON with fields such as:

```json
{
  "auto_upgrade_enabled": true,
  "channel": "latest",
  "source_version": "2.426.3",
  "target_version": "2.462.3",
  "pin_target_version": false,
  "java_preflight_required": false,
  "backup_required": false,
  "required_backup_snapshot": "",
  "abort_on_failed_preflight": false,
  "lock_strategy": "..."
}
```

## Expected result

After M4, diagnostics must no longer stop at phase `UNSAFE_AUTOMATION`. Later phases may still fail.

## Requirements tested in M4

1. Every M1, M2, and M3 requirement remains satisfied.
2. Unguarded automatic upgrade is disabled for the recovered controller.
3. The target version remains pinned to `2.462.3`.
4. The policy uses a pinned LTS-style channel instead of a moving `latest` channel.
5. Java compatibility preflight is mandatory before future upgrades.
6. A backup snapshot is mandatory before future upgrades.
7. The required backup snapshot exists under `/app/backups/`.
8. Failed preflight must abort an upgrade decision.
9. The policy defines a safe upgrade-lock lifecycle for verified restore.
10. The recovery does not hide the outage by deleting upgrade policy evidence.
