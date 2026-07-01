import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { renderPolicy } from "./render_policy.mjs";

function root() {
  return process.env.APP_ROOT || "/app";
}
function readJSON(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}
function stableWrite(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function materializeDesired(desired, queues, aliases) {
  const source = desired.mapping;
  const functionName = source.function_name_from_alias;
  const alias = aliases[functionName];
  return {
    uuid: source.uuid,
    enabled: source.enabled,
    function_name: alias.qualified_target,
    event_source_arn: queues[source.event_source_from_queue],
    batch_size: source.batch_size,
    maximum_batching_window_seconds: source.maximum_batching_window_seconds,
    function_response_types: source.function_response_types,
    source_access_configurations: source.source_access_configurations,
    scaling_config: source.scaling_config,
    filter_criteria: source.filter_criteria,
    bisect_batch_on_function_error: source.bisect_batch_on_function_error,
  };
}

export function reconcile() {
  const app = root();
  const desired = readJSON(join(app, "control_plane", "mapping_desired.json"));
  const checkpoint = readJSON(join(app, "control_plane", "rollout_checkpoint.json"));
  const aliases = readJSON(join(app, "control_plane", "alias_manifest.json"));
  const queues = readJSON(join(app, "config", "queues.json"));

  const mapping = checkpoint.phase === "rollback_pending"
    ? checkpoint.mapping
    : materializeDesired(desired, queues, aliases);

  stableWrite(join(app, "config", "event_source_mapping.json"), mapping);
  renderPolicy();
  return mapping;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  reconcile();
}
