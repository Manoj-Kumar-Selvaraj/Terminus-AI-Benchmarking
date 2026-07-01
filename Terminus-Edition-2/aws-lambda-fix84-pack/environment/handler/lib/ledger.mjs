import { readFileSync, writeFileSync } from "node:fs";

export function ledgerPath() {
  return process.env.SIDE_EFFECT_LEDGER || `${process.env.APP_ROOT || "/app"}/data/side_effect_ledger.json`;
}

export function loadLedger() {
  try {
    const parsed = JSON.parse(readFileSync(ledgerPath(), "utf8"));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export async function commitRecord(entry) {
  const entries = loadLedger();
  entries.push(entry);
  writeFileSync(ledgerPath(), `${JSON.stringify(entries, null, 2)}\n`);
}
