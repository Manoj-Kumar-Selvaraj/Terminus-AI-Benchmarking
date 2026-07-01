import { MessageFailure } from "./errors.mjs";
import { processRecord } from "./process_record.mjs";

export async function processBatch(records) {
  try {
    await Promise.all(records.map((record) => processRecord(record)));
    return { batchItemFailures: [] };
  } catch (error) {
    if (error instanceof MessageFailure) {
      return {
        batchItemFailures: records.map((record) => ({
          itemIdentifier: record.messageId,
        })),
      };
    }
    return {
      batchItemFailures: records.map((record) => ({
        itemIdentifier: record.messageId,
      })),
    };
  }
}
