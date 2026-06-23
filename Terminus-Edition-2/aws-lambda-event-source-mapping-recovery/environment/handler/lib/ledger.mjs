import { readFileSync, writeFileSync } from "node:fs";

export function ledgerPath() {
  return process.env.SIDE_EFFECT_LEDGER || "/app/data/side_effect_ledger.json";
}

export function loadLedger() {
  try {
    return JSON.parse(readFileSync(ledgerPath(), "utf8"));
  } catch {
    return [];
  }
}

export function appendLedgerEntry(entry) {
  const entries = loadLedger();
  entries.push(entry);
  writeFileSync(ledgerPath(), `${JSON.stringify(entries, null, 2)}\n`);
}
