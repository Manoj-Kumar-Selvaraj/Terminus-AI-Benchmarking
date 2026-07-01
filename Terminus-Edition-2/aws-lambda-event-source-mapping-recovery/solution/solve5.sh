#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/solve4.sh"
mkdir -p "$APP_ROOT/handler/lib"
cat > "$APP_ROOT/handler/lib/ledger.mjs" <<'ORACLE_5_6_EOF'
import { createHash } from "node:crypto";
import { MessageFailure } from "./errors.mjs";
import { acquireFileLock } from "./lock.mjs";
import {
  appendJournalSnapshot,
  atomicWriteSnapshot,
  journalPath,
  lockPath,
  nextSequence,
  recoverSnapshot,
} from "./journal.mjs";

export function ledgerPath() {
  return process.env.SIDE_EFFECT_LEDGER || `${process.env.APP_ROOT || "/app"}/data/side_effect_ledger.json`;
}
export function loadLedger() { return recoverSnapshot(ledgerPath()); }

function digestFields(value) {
  return createHash("sha256").update(JSON.stringify([
    value.account_id,
    value.amount_cents,
    value.currency,
    value.operation,
  ])).digest("hex");
}

export async function transactLedger(mutator, { crashPoint = "" } = {}) {
  const path = ledgerPath();
  const release = await acquireFileLock(lockPath(path));
  try {
    const entries = recoverSnapshot(path);
    const outcome = await mutator(entries);
    if (!outcome?.changed) return outcome?.value;
    const journal = journalPath(path);
    appendJournalSnapshot(journal, nextSequence(journal), entries);
    if (crashPoint === "after_journal_commit") process.exit(86);
    atomicWriteSnapshot(path, entries, crashPoint);
    if (crashPoint === "after_ledger_commit") process.exit(88);
    return outcome.value;
  } finally {
    release();
  }
}

export async function commitRecord(entry, options = {}) {
  const {
    crashPoint = "",
    payloadDigest = digestFields(entry),
    conflictReason = "IDEMPOTENCY_CONFLICT",
    requiredOperation,
    unsupportedOperationReason = "UNSUPPORTED_OPERATION",
  } = options;
  return transactLedger((entries) => {
    const existing = entries.find((candidate) => candidate.business_event_id === entry.business_event_id);
    if (existing) {
      const committedDigest = existing.payload_digest || digestFields(existing);
      if (committedDigest !== payloadDigest) {
        throw new MessageFailure(conflictReason, { exposeClassification: true });
      }
      const alternates = Array.isArray(existing.duplicate_message_ids)
        ? existing.duplicate_message_ids
        : [];
      if (entry.message_id !== existing.message_id && !alternates.includes(entry.message_id)) {
        alternates.push(entry.message_id);
        existing.duplicate_message_ids = alternates;
        return { changed: true, value: { duplicate: true, entry: existing } };
      }
      existing.duplicate_message_ids = alternates;
      return { changed: false, value: { duplicate: true, entry: existing } };
    }
    if (requiredOperation !== undefined && entry.operation !== requiredOperation) {
      throw new MessageFailure(unsupportedOperationReason, { exposeClassification: true });
    }
    entries.push({
      ...entry,
      payload_digest: payloadDigest,
      duplicate_message_ids: [...(entry.duplicate_message_ids || [])],
    });
    return { changed: true, value: { duplicate: false, entry } };
  }, { crashPoint });
}
ORACLE_5_6_EOF

cat > "$APP_ROOT/handler/lib/process_record.mjs" <<'ORACLE_5_7_EOF'
import { createHash } from "node:crypto";
import { validateRecord } from "./validate.mjs";
import { commitRecord } from "./ledger.mjs";
import { decodeAndFence } from "./protocol.mjs";

function crashPoint(body) {
  if (body.fixture_crash_after_journal_commit === true) return "after_journal_commit";
  if (body.fixture_crash_during_ledger_replace === true) return "during_ledger_replace";
  if (body.fixture_crash_after_commit === true) return "after_ledger_commit";
  return "";
}
function payloadDigest(body) {
  return createHash("sha256").update(JSON.stringify([
    body.account_id,
    body.amount_cents,
    body.currency,
    body.operation,
  ])).digest("hex");
}

export async function processRecord(record) {
  const { body, contract } = decodeAndFence(record);
  await validateRecord(body);
  await commitRecord({
    message_id: record.messageId,
    business_event_id: body.business_event_id,
    account_id: body.account_id,
    amount_cents: body.amount_cents,
    currency: body.currency,
    operation: body.operation,
    status: "COMMITTED",
    duplicate_message_ids: [],
  }, {
    crashPoint: crashPoint(body),
    payloadDigest: payloadDigest(body),
    conflictReason: contract.failure_classifications.idempotency_conflict,
    requiredOperation: contract.required_operation,
    unsupportedOperationReason: contract.failure_classifications.unsupported_operation,
  });
}
ORACLE_5_7_EOF

cat > "$APP_ROOT/handler/lib/protocol.mjs" <<'ORACLE_5_11_EOF'
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { decodeBody } from "./decode.mjs";
import { MessageFailure } from "./errors.mjs";

function appRoot() { return process.env.APP_ROOT || "/app"; }

export function loadCutoverContract() {
  return JSON.parse(readFileSync(join(appRoot(), "config", "cutover_contract.json"), "utf8"));
}

function canonicalBody(raw, version) {
  if (version === 2 && raw.detail && typeof raw.detail === "object" && !Array.isArray(raw.detail)) {
    return {
      ...raw.detail,
      event_version: version,
      cutover_epoch: raw.cutover_epoch,
      poison: raw.poison,
      failure_reason: raw.failure_reason,
      fixture_delay_ms: raw.fixture_delay_ms,
      fixture_infrastructure_failure: raw.fixture_infrastructure_failure,
      fixture_crash_after_journal_commit: raw.fixture_crash_after_journal_commit,
      fixture_crash_during_ledger_replace: raw.fixture_crash_during_ledger_replace,
      fixture_crash_after_commit: raw.fixture_crash_after_commit,
    };
  }
  return raw;
}

export function decodeAndFence(record) {
  const contract = loadCutoverContract();
  if (record?.eventSourceARN !== contract.active_source_queue_arn) {
    throw new MessageFailure(contract.failure_classifications.stale_source, { exposeClassification: true });
  }
  const raw = decodeBody(record);
  const version = raw.event_version ?? contract.missing_event_version_defaults_to;
  if (!contract.accepted_event_versions.includes(version)) {
    throw new MessageFailure(contract.failure_classifications.unsupported_version, { exposeClassification: true });
  }
  if (version === 2 && raw.cutover_epoch !== contract.cutover_epoch) {
    throw new MessageFailure(contract.failure_classifications.stale_epoch, { exposeClassification: true });
  }
  return { body: canonicalBody(raw, version), contract, version };
}
ORACLE_5_11_EOF
