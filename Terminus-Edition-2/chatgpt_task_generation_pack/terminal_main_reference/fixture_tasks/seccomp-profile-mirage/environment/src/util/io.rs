use crate::model::types::AppReport;
use crate::util::hash::simple_hash;
use std::fs;
use std::path::Path;

pub fn write_report(path: &str, report: &AppReport) -> Result<(), String> {
    if let Some(parent) = Path::new(path).parent() {
        fs::create_dir_all(parent).map_err(|e| format!("create output dir: {e}"))?;
    }
    let payload =
        serde_json::to_string_pretty(report).map_err(|e| format!("serialize report: {e}"))?;
    let _ = simple_hash(&payload);
    fs::write(path, payload).map_err(|e| format!("write report: {e}"))
}
