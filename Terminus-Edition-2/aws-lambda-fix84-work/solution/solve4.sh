#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/solve3.sh"
mkdir -p "$APP_ROOT/handler/lib"
mkdir -p "$APP_ROOT/simulator"
cat > "$APP_ROOT/handler/lib/lock.mjs" <<'ORACLE_4_4_EOF'
import { closeSync, openSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function staleLock(path, staleMs) {
  try {
    const value = JSON.parse(readFileSync(path, "utf8"));
    const age = Date.now() - Number(value.created_ms || 0);
    return age > staleMs || !processAlive(Number(value.pid));
  } catch {
    return true;
  }
}

export async function acquireFileLock(path, { timeoutMs = 5000, staleMs = 30000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      const fd = openSync(path, "wx", 0o600);
      writeFileSync(fd, `${JSON.stringify({ pid: process.pid, created_ms: Date.now() })}\n`);
      closeSync(fd);
      let released = false;
      return () => {
        if (released) return;
        released = true;
        try { unlinkSync(path); } catch (error) {
          if (error?.code !== "ENOENT") throw error;
        }
      };
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      if (staleLock(path, staleMs)) {
        try { unlinkSync(path); } catch (unlinkError) {
          if (unlinkError?.code !== "ENOENT") throw unlinkError;
        }
        continue;
      }
      if (Date.now() >= deadline) throw new Error(`timed out acquiring ledger lock ${path}`);
      await sleep(10);
    }
  }
}
ORACLE_4_4_EOF

cat > "$APP_ROOT/handler/lib/journal.mjs" <<'ORACLE_4_5_EOF'
import { createHash } from "node:crypto";
import {
  appendFileSync,
  closeSync,
  existsSync,
  fsyncSync,
  openSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { dirname } from "node:path";

function digest(seq, snapshot) {
  return createHash("sha256").update(JSON.stringify({ seq, snapshot })).digest("hex");
}

export function journalPath(ledger) { return `${ledger}.journal`; }
export function lockPath(ledger) { return `${ledger}.lock`; }

export function readJournal(path) {
  if (!existsSync(path)) return [];
  const text = readFileSync(path, "utf8");
  const complete = text.endsWith("\n");
  const parts = text.split("\n");
  if (!complete) parts.pop();
  const records = [];
  for (const [index, line] of parts.entries()) {
    if (!line.trim()) continue;
    let record;
    try { record = JSON.parse(line); } catch {
      throw new Error(`journal corruption at committed line ${index + 1}`);
    }
    if (!Number.isInteger(record.seq) || !Array.isArray(record.snapshot)) {
      throw new Error(`journal corruption at committed line ${index + 1}`);
    }
    if (records.length && record.seq !== records.at(-1).seq + 1) {
      throw new Error(`journal sequence gap at committed line ${index + 1}`);
    }
    if (record.checksum !== digest(record.seq, record.snapshot)) {
      throw new Error(`journal checksum mismatch at committed line ${index + 1}`);
    }
    records.push(record);
  }
  return records;
}

export function readLedgerSnapshot(path) {
  try {
    const value = JSON.parse(readFileSync(path, "utf8"));
    if (!Array.isArray(value)) throw new Error("ledger is not a flat array");
    return value;
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
}

export function recoverSnapshot(ledger) {
  const records = readJournal(journalPath(ledger));
  let disk;
  let diskError;
  try { disk = readLedgerSnapshot(ledger); } catch (error) { diskError = error; }
  if (records.length > 0) {
    const latest = records.at(-1).snapshot;
    if (diskError || JSON.stringify(disk) !== JSON.stringify(latest)) {
      atomicWriteSnapshot(ledger, latest);
    }
    return structuredClone(latest);
  }
  if (diskError) throw new Error(`ledger corruption without recoverable journal: ${diskError.message}`);
  return structuredClone(disk);
}

export function appendJournalSnapshot(path, seq, snapshot) {
  const record = { seq, snapshot, checksum: digest(seq, snapshot) };
  const fd = openSync(path, "a", 0o600);
  try {
    appendFileSync(fd, `${JSON.stringify(record)}\n`);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
}

export function nextSequence(path) {
  const records = readJournal(path);
  return records.length ? records.at(-1).seq + 1 : 1;
}

export function atomicWriteSnapshot(path, snapshot, crashPoint = "") {
  const temp = `${path}.tmp.${process.pid}`;
  const fd = openSync(temp, "w", 0o600);
  try {
    writeFileSync(fd, `${JSON.stringify(snapshot, null, 2)}\n`);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  if (crashPoint === "during_ledger_replace") process.exit(87);
  renameSync(temp, path);
  try {
    const dirfd = openSync(dirname(path), "r");
    fsyncSync(dirfd);
    closeSync(dirfd);
  } catch {
    // Some filesystems do not permit directory fsync; the atomic rename remains valid.
  }
}
ORACLE_4_5_EOF

cat > "$APP_ROOT/handler/lib/ledger.mjs" <<'ORACLE_4_6_EOF'
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

export function loadLedger() {
  return recoverSnapshot(ledgerPath());
}

export async function transactLedger(mutator, { crashPoint = "" } = {}) {
  const path = ledgerPath();
  const release = await acquireFileLock(lockPath(path));
  try {
    const entries = recoverSnapshot(path);
    const outcome = await mutator(entries);
    if (!outcome?.changed) return outcome?.value;
    const journal = journalPath(path);
    const seq = nextSequence(journal);
    appendJournalSnapshot(journal, seq, entries);
    if (crashPoint === "after_journal_commit") process.exit(86);
    atomicWriteSnapshot(path, entries, crashPoint);
    if (crashPoint === "after_ledger_commit") process.exit(88);
    return outcome.value;
  } finally {
    release();
  }
}

export async function commitRecord(entry, options = {}) {
  const crashPoint = options.crashPoint || "";
  return transactLedger((entries) => {
    const existing = entries.find((candidate) => candidate.business_event_id === entry.business_event_id);
    if (existing) {
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
    entries.push({ ...entry, duplicate_message_ids: [...(entry.duplicate_message_ids || [])] });
    return { changed: true, value: { duplicate: false, entry } };
  }, { crashPoint });
}
ORACLE_4_6_EOF

cat > "$APP_ROOT/handler/lib/process_record.mjs" <<'ORACLE_4_7_EOF'
import { decodeBody } from "./decode.mjs";
import { validateRecord } from "./validate.mjs";
import { commitRecord } from "./ledger.mjs";

function crashPoint(body) {
  if (body.fixture_crash_after_journal_commit === true) return "after_journal_commit";
  if (body.fixture_crash_during_ledger_replace === true) return "during_ledger_replace";
  if (body.fixture_crash_after_commit === true) return "after_ledger_commit";
  return "";
}

export async function processRecord(record) {
  const body = decodeBody(record);
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
  }, { crashPoint: crashPoint(body) });
}
ORACLE_4_7_EOF

cat > "$APP_ROOT/simulator/paths.go" <<'ORACLE_4_8_EOF'
package main

import (
	"os"
	"path/filepath"
)

func appRoot() string {
	if value := os.Getenv("APP_ROOT"); value != "" {
		return value
	}
	return "/app"
}

func configPath(name string) string { return filepath.Join(appRoot(), "config", name) }
func dataPath(name string) string   { return filepath.Join(appRoot(), "data", name) }

func ledgerPath() string {
	if value := os.Getenv("SIDE_EFFECT_LEDGER"); value != "" {
		return value
	}
	return dataPath("side_effect_ledger.json")
}

func dlqPath() string {
	if value := os.Getenv("DLQ_STATE"); value != "" {
		return value
	}
	return dataPath("dlq_state.json")
}

func deliveryStatePath() string {
	if value := os.Getenv("DELIVERY_STATE"); value != "" {
		return value
	}
	if value := os.Getenv("DLQ_STATE"); value != "" {
		return value + ".delivery.json"
	}
	return dataPath("delivery_state.json")
}
ORACLE_4_8_EOF

cat > "$APP_ROOT/simulator/state.go" <<'ORACLE_4_9_EOF'
package main

import "os"

type deliveryState struct {
	ReceiveCounts map[string]int  `json:"receive_counts"`
	Retired       map[string]bool `json:"retired"`
}

func loadLedger() ([]map[string]any, error) { return loadJSONArray(ledgerPath()) }
func loadDLQ() ([]map[string]any, error)    { return loadJSONArray(dlqPath()) }

func appendDLQEntry(entry map[string]any) (bool, error) {
	entries, err := loadDLQ()
	if err != nil {
		return false, err
	}
	original := stringValue(entry["original_message_id"])
	for _, existing := range entries {
		if stringValue(existing["original_message_id"]) == original {
			return false, nil
		}
	}
	entries = append(entries, entry)
	return true, saveJSON(dlqPath(), entries)
}

func loadDeliveryState() (deliveryState, error) {
	state := deliveryState{ReceiveCounts: map[string]int{}, Retired: map[string]bool{}}
	if _, err := os.Stat(deliveryStatePath()); os.IsNotExist(err) {
		return state, nil
	}
	if err := loadJSON(deliveryStatePath(), &state); err != nil {
		return deliveryState{}, err
	}
	if state.ReceiveCounts == nil {
		state.ReceiveCounts = map[string]int{}
	}
	if state.Retired == nil {
		state.Retired = map[string]bool{}
	}
	return state, nil
}

func saveDeliveryState(state deliveryState) error { return saveJSON(deliveryStatePath(), state) }
ORACLE_4_9_EOF

cat > "$APP_ROOT/simulator/simulator.go" <<'ORACLE_4_10_EOF'
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
)

func stringValue(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case nil:
		return ""
	default:
		return fmt.Sprint(typed)
	}
}

func intValue(value any, fallback int) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case float32:
		return int(typed)
	case int:
		return typed
	case int64:
		return int(typed)
	case json.Number:
		parsed, err := typed.Int64()
		if err == nil {
			return int(parsed)
		}
	case string:
		parsed, err := strconv.Atoi(typed)
		if err == nil {
			return parsed
		}
	}
	return fallback
}

func cloneMap(input map[string]any) map[string]any {
	data, _ := json.Marshal(input)
	var output map[string]any
	_ = json.Unmarshal(data, &output)
	return output
}

func loadRuntime() (map[string]any, map[string]any, map[string]any, error) {
	mapping, queues, policy := map[string]any{}, map[string]any{}, map[string]any{}
	if err := loadJSON(configPath("event_source_mapping.json"), &mapping); err != nil {
		return nil, nil, nil, err
	}
	if err := loadJSON(configPath("queues.json"), &queues); err != nil {
		return nil, nil, nil, err
	}
	if err := loadJSON(configPath("lambda_role_policy.json"), &policy); err != nil {
		return nil, nil, nil, err
	}
	return mapping, queues, policy, nil
}

func mappingProbe() (map[string]any, error) {
	mapping, queues, _, err := loadRuntime()
	if err != nil {
		return nil, err
	}
	return activeMapping(mapping, queues), nil
}

func iamProbe() (map[string]any, error) {
	_, queues, policy, err := loadRuntime()
	if err != nil {
		return nil, err
	}
	queueARN := stringValue(queues["expected_active_queue_arn"])
	return map[string]any{
		"queue_arn":           queueARN,
		"decisions":           requiredSQSDecisions(policy, queueARN),
		"old_queue_receive":   decide(policy, "sqs:ReceiveMessage", stringValue(queues["old_queue_arn"])),
		"has_broad_sqs_grant": hasBroadSQSGrant(policy),
		"has_log_permissions": hasLogPermissions(policy),
	}, nil
}

func eventRecords(messages []map[string]any, state deliveryState) []map[string]any {
	records := make([]map[string]any, 0, len(messages))
	for _, message := range messages {
		cloned := cloneMap(message)
		mid := stringValue(message["messageId"])
		attrs, _ := cloned["attributes"].(map[string]any)
		if attrs == nil {
			attrs = map[string]any{}
		}
		attrs["ApproximateReceiveCount"] = strconv.Itoa(state.ReceiveCounts[mid])
		cloned["attributes"] = attrs
		records = append(records, cloned)
	}
	return records
}

func messageReason(message map[string]any) string {
	bodyText := stringValue(message["body"])
	body := map[string]any{}
	if err := json.Unmarshal([]byte(bodyText), &body); err != nil {
		return "MALFORMED_JSON"
	}
	if poison, _ := body["poison"].(bool); poison {
		if reason := stringValue(body["failure_reason"]); reason != "" {
			return reason
		}
		return "POISON_MESSAGE"
	}
	return "PROCESSING_FAILED"
}

func messageSlice(value any) []map[string]any {
	raw, _ := value.([]any)
	messages := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if message, ok := item.(map[string]any); ok {
			messages = append(messages, cloneMap(message))
		}
	}
	return messages
}

func resultWithState(result map[string]any) (map[string]any, error) {
	ledger, err := loadLedger()
	if err != nil {
		return nil, err
	}
	dlq, err := loadDLQ()
	if err != nil {
		return nil, err
	}
	result["ledger_entries"] = ledger
	result["dlq_entries"] = dlq
	return result, nil
}

func simulateBatch(batchFile string, cycles int) (map[string]any, error) {
	mapping, queues, policy, err := loadRuntime()
	if err != nil {
		return nil, err
	}
	mapInfo := activeMapping(mapping, queues)
	batch := map[string]any{}
	if err := loadJSON(batchFile, &batch); err != nil {
		return nil, err
	}
	redrive := map[string]any{}
	if err := loadJSON(configPath("redrive_policy.json"), &redrive); err != nil {
		return nil, err
	}
	queueARN := stringValue(batch["queue_arn"])
	if queueARN == "" {
		queueARN = stringValue(queues["expected_active_queue_arn"])
	}
	result := map[string]any{
		"mapping": mapInfo, "queue_arn": queueARN, "cycles": []any{}, "access_denied": false,
		"access_denied_actions": []any{}, "delivered_message_ids": []any{}, "deleted_message_ids": []any{},
		"failed_message_ids": []any{}, "receive_counts": map[string]any{}, "dlq_message_ids": []any{},
	}

	expectedARN := stringValue(queues["expected_active_queue_arn"])
	required := requiredSQSDecisions(policy, expectedARN)
	denied := []any{}
	for _, action := range requiredSQSActions {
		if stringValue(required[action]) != "allowed" {
			denied = append(denied, action)
		}
	}
	if len(denied) > 0 {
		result["access_denied"], result["access_denied_actions"] = true, denied
		return resultWithState(result)
	}
	active, _ := mapInfo["active"].(bool)
	if !active || queueARN != expectedARN {
		return resultWithState(result)
	}

	messages := messageSlice(batch["messages"])
	maxReceive := intValue(redrive["max_receive_count"], 3)
	state, err := loadDeliveryState()
	if err != nil {
		return nil, err
	}
	currentDLQ, err := loadDLQ()
	if err != nil {
		return nil, err
	}
	for _, entry := range currentDLQ {
		if original := stringValue(entry["original_message_id"]); original != "" {
			state.Retired[original] = true
		}
	}
	if err := saveDeliveryState(state); err != nil {
		return nil, err
	}

	for cycle := 0; cycle < cycles; cycle++ {
		available := make([]map[string]any, 0, len(messages))
		for _, message := range messages {
			if !state.Retired[stringValue(message["messageId"])] {
				available = append(available, message)
			}
		}
		cyclesOut := result["cycles"].([]any)
		if len(available) == 0 {
			result["cycles"] = append(cyclesOut, map[string]any{"delivered": []any{}, "failed": []any{}, "deleted": []any{}})
			continue
		}
		batchSize := intValue(mapping["batch_size"], 10)
		if batchSize > len(available) {
			batchSize = len(available)
		}
		delivered := available[:batchSize]
		for _, message := range delivered {
			mid := stringValue(message["messageId"])
			state.ReceiveCounts[mid]++
			result["receive_counts"].(map[string]any)[mid] = state.ReceiveCounts[mid]
		}
		if err := saveDeliveryState(state); err != nil {
			return nil, err
		}
		records := eventRecords(delivered, state)
		rawRecords := make([]any, 0, len(records))
		for _, record := range records {
			rawRecords = append(rawRecords, record)
		}
		response, err := handleBatch(map[string]any{"Records": rawRecords})
		if err != nil {
			return nil, err
		}
		failedIDs := map[string]bool{}
		if rawFailures, ok := response["batchItemFailures"].([]any); ok {
			for _, rawFailure := range rawFailures {
				if failure, ok := rawFailure.(map[string]any); ok {
					failedIDs[stringValue(failure["itemIdentifier"])] = true
				}
			}
		}
		cycleDeleted, cycleFailed := []any{}, []any{}
		deliveredIDs := make([]any, 0, len(delivered))
		for _, message := range delivered {
			mid := stringValue(message["messageId"])
			deliveredIDs = append(deliveredIDs, mid)
			result["delivered_message_ids"] = append(result["delivered_message_ids"].([]any), mid)
			if failedIDs[mid] {
				result["failed_message_ids"] = append(result["failed_message_ids"].([]any), mid)
				cycleFailed = append(cycleFailed, mid)
				if state.ReceiveCounts[mid] >= maxReceive {
					var eventID any
					body := map[string]any{}
					if err := json.Unmarshal([]byte(stringValue(message["body"])), &body); err == nil {
						eventID = body["business_event_id"]
					}
					appended, err := appendDLQEntry(map[string]any{
						"message_id": "dlq-" + mid, "original_message_id": mid, "business_event_id": eventID,
						"source_queue_arn": queueARN, "failure_reason": messageReason(message), "receive_count": state.ReceiveCounts[mid],
					})
					if err != nil {
						return nil, err
					}
					if appended && os.Getenv("SIMULATOR_CRASH_POINT") == "after_dlq_append" {
						return nil, fmt.Errorf("injected crash after DLQ append")
					}
					state.Retired[mid] = true
					result["dlq_message_ids"] = append(result["dlq_message_ids"].([]any), mid)
				}
			} else {
				state.Retired[mid] = true
				result["deleted_message_ids"] = append(result["deleted_message_ids"].([]any), mid)
				cycleDeleted = append(cycleDeleted, mid)
			}
		}
		if err := saveDeliveryState(state); err != nil {
			return nil, err
		}
		result["cycles"] = append(cyclesOut, map[string]any{"delivered": deliveredIDs, "failed": cycleFailed, "deleted": cycleDeleted})
	}
	return resultWithState(result)
}
ORACLE_4_10_EOF

gofmt -w "$APP_ROOT/simulator"/*.go
rm -f "$APP_ROOT/tmp/run_simulation-current"
