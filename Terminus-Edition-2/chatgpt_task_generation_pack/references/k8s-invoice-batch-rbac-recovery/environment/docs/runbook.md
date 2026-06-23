# Runbook

## Validate manifest bundle

```bash
/app/scripts/run_simulation.sh all
```

## Inspect authorization chain

Review `/app/manifests/serviceaccount.yaml`, `/app/manifests/rolebinding.yaml`, `/app/manifests/role.yaml`, and `/app/manifests/cronjob.yaml`.

Confirm the CronJob service account matches the RoleBinding subject and that the bound Role allows ConfigMap reads required by the batch contract.

## Inspect overlap behavior

Review `/app/manifests/cronjob.yaml` concurrency settings against `/app/docs/publication_contract.md`.

## Inspect least privilege

Compare Role rules against `/app/docs/rbac_contract.md` after functional recovery.
