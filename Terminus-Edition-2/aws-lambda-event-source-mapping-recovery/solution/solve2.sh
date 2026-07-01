#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$APP_ROOT/control_plane"
cat > "$APP_ROOT/control_plane/reconcile.mjs" <<'ORACLE_2_1_EOF'
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { renderPolicy } from "./render_policy.mjs";

function root() { return process.env.APP_ROOT || "/app"; }
function readJSON(path) { return JSON.parse(readFileSync(path, "utf8")); }
function stableWrite(path, value) { writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`); }

function materializeDesired(desired, queues, aliases) {
  const source = desired.mapping;
  const alias = aliases[source.function_name_from_alias];
  if (!alias?.qualified_target) throw new Error("active alias target is missing");
  const eventSourceARN = queues[source.event_source_from_queue];
  if (!eventSourceARN) throw new Error("active queue reference is missing");
  return {
    uuid: source.uuid,
    enabled: source.enabled,
    function_name: alias.qualified_target,
    event_source_arn: eventSourceARN,
    batch_size: source.batch_size,
    maximum_batching_window_seconds: source.maximum_batching_window_seconds,
    function_response_types: [...source.function_response_types],
    source_access_configurations: [...source.source_access_configurations],
    scaling_config: { ...source.scaling_config },
    filter_criteria: JSON.parse(JSON.stringify(source.filter_criteria)),
    bisect_batch_on_function_error: source.bisect_batch_on_function_error,
  };
}

function completed(candidate) {
  return candidate && ["completed", "active"].includes(candidate.phase);
}

export function reconcile() {
  const app = root();
  const desired = readJSON(join(app, "control_plane", "mapping_desired.json"));
  const checkpoint = readJSON(join(app, "control_plane", "rollout_checkpoint.json"));
  const aliases = readJSON(join(app, "control_plane", "alias_manifest.json"));
  const queues = readJSON(join(app, "config", "queues.json"));

  const candidates = [
    completed(desired) ? { generation: Number(desired.generation), kind: "desired", value: desired } : null,
    completed(checkpoint) ? { generation: Number(checkpoint.generation), kind: "checkpoint", value: checkpoint } : null,
  ].filter(Boolean).sort((a, b) => b.generation - a.generation);
  if (candidates.length === 0) throw new Error("no completed mapping generation is available");

  const winner = candidates[0];
  const mapping = winner.kind === "desired"
    ? materializeDesired(winner.value, queues, aliases)
    : JSON.parse(JSON.stringify(winner.value.mapping));

  stableWrite(join(app, "config", "event_source_mapping.json"), mapping);
  renderPolicy();
  return mapping;
}

if (import.meta.url === `file://${process.argv[1]}`) reconcile();
ORACLE_2_1_EOF

cat > "$APP_ROOT/control_plane/render_policy.mjs" <<'ORACLE_2_2_EOF'
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

function root() { return process.env.APP_ROOT || "/app"; }
function readJSON(path) { return JSON.parse(readFileSync(path, "utf8")); }
function stableWrite(path, value) { writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`); }

export function renderPolicy() {
  const app = root();
  const base = readJSON(join(app, "control_plane", "policy_base.json"));
  const grantSet = readJSON(join(app, "control_plane", "queue_grants.json"));
  const queues = readJSON(join(app, "config", "queues.json"));
  const active = grantSet.grants
    .filter((grant) => grant.status === "active")
    .sort((a, b) => Number(b.generation) - Number(a.generation));
  if (active.length === 0) throw new Error("no active queue grant is available");
  const generation = Number(active[0].generation);
  const winners = active.filter((grant) => Number(grant.generation) === generation);
  if (winners.length !== 1) throw new Error("active queue grant generation is ambiguous");
  const grant = winners[0];
  const resource = queues[grant.queue_ref];
  if (!resource) throw new Error(`unknown queue reference: ${grant.queue_ref}`);
  const actions = [...new Set(grant.actions)];
  const rendered = {
    Version: base.Version,
    Statement: [
      ...base.Statement.map((statement) => JSON.parse(JSON.stringify(statement))),
      { Sid: grant.sid, Effect: "Allow", Action: actions, Resource: resource },
    ],
  };
  stableWrite(join(app, "config", "lambda_role_policy.json"), rendered);
  return rendered;
}

if (import.meta.url === `file://${process.argv[1]}`) renderPolicy();
ORACLE_2_2_EOF

APP_ROOT="$APP_ROOT" node "$APP_ROOT/control_plane/reconcile.mjs"
