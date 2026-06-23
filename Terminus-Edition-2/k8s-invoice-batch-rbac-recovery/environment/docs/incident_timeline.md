# Incident Timeline

## 2026-06-11 02:04 UTC — Authorization failure

Nightly invoice batch pods exit before publication. API audit shows repeated `Forbidden` responses while reading `invoice-batch-config`.

## 2026-06-12 02:11 UTC — Duplicate ledger artifacts

After on-call restored configuration reads, finance detected two ledger Secrets for `WIN-20260612` during a single nightly cycle. The first job was still running when the next schedule slot fired.

## 2026-06-12 15:30 UTC — Security review

Platform security requested least-privilege tightening on the batch Role before promoting the concurrency fix to production.
