# Queue migration contract

The live payments ingestion alias remains `payments-ledger-ingestor:live`. The migrated queue is `payments-ledger-v2`; the old queue may remain in configuration for audits but must not feed active processing. Queue permissions must be scoped to the migrated queue ARN and must not be broadened to wildcard action or resource grants. Existing CloudWatch Logs permissions are unrelated to queue polling and must remain present.
