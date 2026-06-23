Security review flagged excessive API permissions on the batch Role while approving the concurrency fix. Review `/app/docs/rbac_contract.md` and the manifest bundle under `/app/manifests`.

Reduce permissions to the minimum needed for configuration reads and ledger publication while preserving milestone 1 authorization and milestone 2 single-publication behavior. The final Role must have no wildcards and exactly two rules:

- `configmaps` with verb `get`, scoped with `resourceNames: ["invoice-batch-config"]`
- `secrets` with verbs `create` and `get`
