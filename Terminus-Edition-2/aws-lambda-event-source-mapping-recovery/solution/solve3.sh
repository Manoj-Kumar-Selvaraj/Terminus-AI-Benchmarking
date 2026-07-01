#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/solve2.sh"
mkdir -p "$APP_ROOT/handler/lib"
cat > "$APP_ROOT/handler/lib/batch.mjs" <<'ORACLE_3_3_EOF'
import { MessageFailure } from "./errors.mjs";
import { loadLedger, transactLedger } from "./ledger.mjs";
import { processRecord } from "./process_record.mjs";

export async function processBatch(records) {
  const snapshot = loadLedger();
  const results = await Promise.allSettled(records.map((record) => processRecord(record)));
  const infraError = results.find(
    (result) => result.status === "rejected" && !(result.reason instanceof MessageFailure),
  );
  if (infraError) {
    await transactLedger((entries) => {
      entries.splice(0, entries.length, ...snapshot);
      return { changed: true, value: null };
    });
    throw infraError.reason;
  }
  const failures = [];
  const seen = new Set();
  for (let index = 0; index < results.length; index += 1) {
    const result = results[index];
    if (result.status === "fulfilled") continue;
    const error = result.reason;
    if (!(error instanceof MessageFailure)) throw error;
    const identifier = records[index].messageId;
    if (seen.has(identifier)) continue;
    seen.add(identifier);
    const failure = { itemIdentifier: identifier };
    if (error.exposeClassification) failure.failureClassification = error.reason;
    failures.push(failure);
  }
  return { batchItemFailures: failures };
}
ORACLE_3_3_EOF
