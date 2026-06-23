# RBAC Contract

The nightly invoice batch CronJob runs as `invoice-batch-runner` in `billing-batch`.

Authorization requirements:

- The CronJob pod service account must be the subject of the namespace RoleBinding for `invoice-batch-role`.
- The bound Role must allow `get` on ConfigMap `invoice-batch-config`.
- ConfigMap access must be scoped with `resourceNames: ["invoice-batch-config"]` so the batch identity cannot read unrelated ConfigMaps in the namespace.
- Ledger publication writes Secrets in the same namespace. The Role must allow `create` and `get` on Secrets.

Security review expectations:

- No wildcard `apiGroups`, `resources`, or `verbs`.
- No verbs beyond `get` on ConfigMaps.
- No verbs beyond `create` and `get` on Secrets.
- No access to unrelated API resources.

The offline simulator under `/app/sim` evaluates the manifest bundle against this contract.
