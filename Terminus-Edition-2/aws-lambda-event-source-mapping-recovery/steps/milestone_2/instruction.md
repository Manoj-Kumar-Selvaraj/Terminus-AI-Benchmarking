You are working in `/app`. This is an offline simulator for a payments ledger Lambda that is triggered by SQS after a queue migration. Do not use live AWS credentials or AWS CLI. The production command surface is `/app/scripts/run_simulation.py`; keep the existing config file locations, handler entry point, fixture schemas, and simulator behavior compatible.


The migrated mapping is now visible, but replay still fails with access-denied evidence. Review `/app/config/lambda_role_policy.json`, `/app/evidence/access_denied.log`, and `/app/evidence/iam_decision_table.json`.

Requirements: the Lambda role policy must allow `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, and `sqs:GetQueueAttributes` on the migrated queue ARN. Permissions must not remain scoped only to the old queue ARN. Queue permissions must not be broadened to wildcard action or wildcard resource grants. Existing CloudWatch Logs permissions must remain present. The simulator must be able to deliver and delete messages from the migrated queue without access-denied results, and the old queue must not become the active processing source.
