# Operator Runbook

Commands rebuild the Java source automatically.

```bash
signerctl init --state /tmp/signing --lease-ms 100 --key key-2026-a
signerctl acquire --state /tmp/signing --node signer-a --now 1000 --out /tmp/token.json
signerctl recover --state /tmp/signing --node signer-a --token signer-a:1 --now 1010 --out /tmp/recovery.json
```

Exit code 75 is reserved for deterministic crash injection. Rejected fencing, replay, and policy conditions return another non-zero code and retain their evidence files.
