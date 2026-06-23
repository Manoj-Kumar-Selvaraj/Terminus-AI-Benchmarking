# Partial batch response contract

The simulator models the Lambda/SQS partial batch response shape used by the production runtime. A handler result must be a JSON object with `batchItemFailures` as a list. Each failed record is represented by an object with `itemIdentifier` equal to the SQS `messageId` of the failed record.

Records not listed in `batchItemFailures` are treated as successfully processed and are deleted if queue permissions allow deletion. Records listed in `batchItemFailures` remain eligible for retry until the configured redrive policy moves them to the DLQ.
