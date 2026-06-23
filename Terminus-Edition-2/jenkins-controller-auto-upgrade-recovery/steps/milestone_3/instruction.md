# M3 — Restore plugin baseline for the recovered controller

The controller home is structurally restored, but the recovered target controller still cannot complete plugin initialization. The simulator models essential plugin metadata under Jenkins home and compares it to the target baseline contract.

Evidence is available in:

- `/app/evidence/plugin_load_failure.log`
- `/app/config/version_contract.json`
- `/app/jenkins_home/plugins/plugins.json`


## Shared constraints

- Work under `/app`.
- Use `/app/scripts/run_controller.sh` or `python3 /app/scripts/jenkins_cluster_sim.py diagnose --json` to exercise the offline simulator.
- Do not require a real Jenkins controller, Kubernetes cluster, network access, Jenkins CLI, or cloud credentials.
- Preserve the cluster identity: `prod-ci-east`, namespace `jenkins-prod`, deployment `jenkins-controller`, service `jenkins-web`, and PVC claim `jenkins-home-rwo`.
- Preserve `/app/jenkins_home`; do not replace it with a tiny fake home or delete jobs/credentials.
- Preserve the target Jenkins version `2.462.3` from the incident contract.
- Do not edit tests or simulator output files as a substitute for restoring the simulated system state.


## Input format

`/app/jenkins_home/plugins/plugins.json` is JSON keyed by plugin short name:

```json
{
  "workflow-job": {"version": "...", "enabled": true},
  "credentials-binding": {"version": "...", "enabled": true},
  "matrix-auth": {"version": "...", "enabled": true},
  "git": {"version": "...", "enabled": true}
}
```

The required target plugin baseline is declared in `/app/config/version_contract.json`.

## Expected result

After M3, diagnostics must no longer stop at phase `PLUGIN_INCOMPATIBLE`. Later phases may still fail.

## Requirements tested in M3

1. Every M1 and M2 requirement remains satisfied.
2. All essential plugins listed in the version contract are present.
3. All essential plugins are enabled.
4. Essential plugin versions satisfy the target baseline contract.
5. Plugin compatibility is aligned with the configured Java runtime and target Jenkins version.
6. Optional noisy plugins do not need to drive recovery unless they block simulator readiness; keep `monitoring-theme` present if it already exists in the home snapshot.
7. The solution does not pass by removing essential plugin names from the version contract.
8. Jenkins home recovery evidence remains intact after plugin recovery.
