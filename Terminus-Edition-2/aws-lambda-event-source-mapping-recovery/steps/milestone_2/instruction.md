You are working in `/app`. This is an offline simulator for a payments ledger Lambda that is triggered by SQS after a queue migration. Do not use live AWS credentials or AWS CLI. The production command surface is `/app/scripts/run_simulation.py`; keep the existing config file locations, handler entry point, fixture schemas, and simulator behavior compatible.


The migrated mapping is now visible, but replay still fails with access-denied evidence. Review `/app/config/lambda_role_policy.json`, `/app/evidence/access_denied.log`, and `/app/evidence/iam_decision_table.json`.

Requirements: the Lambda role policy must allow `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, and `sqs:GetQueueAttributes` on the migrated queue ARN. Permissions must not remain scoped only to the old queue ARN; remove old-queue SQS allow statements so `sqs:ReceiveMessage` on the old queue ARN is not authorized. Queue permissions must not be broadened to wildcard action or wildcard resource grants. Existing CloudWatch Logs permissions must remain present. The simulator must be able to deliver and delete messages from the migrated queue without access-denied results, and the old queue must not become the active processing source.


The migrated queue grant must be one exact allow statement containing only the four documented SQS actions and only the migrated queue ARN. Preserve logs permissions separately. Explicit denies are allowed, but an old-queue allow, `NotAction`, `NotResource`, service-wide SQS grant, or mixed old/new resource list is not acceptable.

Do not edit the offline simulator runtime sources under `/app/src/` or `/app/handler/invoke.mjs`; milestone 3 integrity-checks those harness files. Repair `/app/config/lambda_role_policy.json` and preserve milestone 1 mapping behavior.
