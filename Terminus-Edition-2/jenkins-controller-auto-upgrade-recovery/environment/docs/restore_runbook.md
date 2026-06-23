# Restore runbook fragments

The on-call runbook emphasizes preserving `$JENKINS_HOME` contents before changing controller startup settings. The controller home contains job definitions, credentials, update state, plugin metadata, queue records, and upgrade markers.

Do not remove the home directory, delete the PVC identity, or replace persisted configuration with a minimal fake home. Recovery is expected to preserve configured jobs and credentials while clearing or repairing unsafe partial-upgrade state.

A valid restore should leave enough evidence for reviewers to understand which snapshot was used, which files were restored, and which upgrade markers remain intentionally cleared.
