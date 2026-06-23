Security review flagged excessive API permissions on the batch Role while approving the concurrency fix. Review `/app/docs/rbac_contract.md` and the manifest bundle under `/app/manifests`.

Reduce permissions to the minimum needed for configuration reads and ledger publication while preserving milestone 1 authorization and milestone 2 single-publication behavior.
