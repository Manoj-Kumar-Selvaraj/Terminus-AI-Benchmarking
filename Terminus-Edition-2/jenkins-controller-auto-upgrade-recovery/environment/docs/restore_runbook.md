# Restore runbook fragments

The on-call runbook emphasizes preserving `$JENKINS_HOME` contents before changing controller startup settings. The controller home contains job definitions, credentials, update state, plugin metadata, queue records, and upgrade markers.

Do not remove the home directory, delete the PVC identity, or replace persisted configuration with a minimal fake home. Recovery is expected to preserve configured jobs and credentials while clearing or repairing unsafe partial-upgrade state.

A valid restore should leave enough evidence for reviewers to understand which snapshot was used, which files were restored, and which upgrade markers remain intentionally cleared.

After restoring from `/app/backups/pre-upgrade-20260618/`, update `/app/jenkins_home/controller_state.json` so the simulator can distinguish a recovered target home from the failed partial-upgrade state. Required post-restore values:

```json
{
  "previous_version": "2.426.3",
  "target_version": "2.462.3",
  "home_schema": "recovered-target",
  "upgrade_status": "RESTORED",
  "restored_from_snapshot": "pre-upgrade-20260618"
}
```

The `home_schema` value `recovered-target` and non-empty `restored_from_snapshot` are checked by `jenkins_cluster_sim.py` during the `home_integrity` diagnostic.
