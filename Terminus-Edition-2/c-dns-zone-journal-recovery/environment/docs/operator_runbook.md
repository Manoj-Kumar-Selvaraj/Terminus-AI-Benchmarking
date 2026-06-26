# Operator Runbook

Builds are intentionally performed by `/app/bin/zonectl` after source changes.

Typical investigation:

```bash
zonectl query --state /tmp/atlas-state --out /tmp/before.json
zonectl recover --state /tmp/atlas-state --out /tmp/recovered.json
zonectl compact --state /tmp/atlas-state
```

Exit code 75 represents the deterministic crash-injection points used by the incident reproduction. Other non-zero codes represent rejected state or input.
