pub mod model;
pub mod report;
pub mod runtime;
pub mod scenario;
pub mod util;

use model::types::{AppReport, RuntimeConfig};
use scenario::loader::load_scenarios;
use std::fs;

pub fn load_runtime_config(path: &str) -> Result<RuntimeConfig, String> {
    let raw = fs::read_to_string(path).map_err(|e| format!("read config: {e}"))?;
    let mut scenario_root = String::new();
    let mut output_file = String::new();
    for line in raw.lines().map(str::trim) {
        if let Some(value) = line.strip_prefix("scenario_root = ") {
            scenario_root = value.trim_matches('"').to_string();
        }
        if let Some(value) = line.strip_prefix("output_file = ") {
            output_file = value.trim_matches('"').to_string();
        }
    }
    if scenario_root.is_empty() || output_file.is_empty() {
        return Err("missing runtime config keys".to_string());
    }
    Ok(RuntimeConfig {
        scenario_root,
        output_file,
    })
}

pub fn execute_all(cfg: &RuntimeConfig) -> Result<AppReport, String> {
    let scenarios = load_scenarios(&cfg.scenario_root)?;
    runtime::run::execute_scenarios(&scenarios)
}
