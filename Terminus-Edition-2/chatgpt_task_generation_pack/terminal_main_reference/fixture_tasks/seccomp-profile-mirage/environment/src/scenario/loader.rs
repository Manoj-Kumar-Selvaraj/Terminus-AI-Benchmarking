use crate::model::types::ScenarioSpec;
use std::fs;
use std::path::Path;

pub fn load_scenarios(root: &str) -> Result<Vec<ScenarioSpec>, String> {
    let root_path = Path::new(root);
    let mut files = Vec::new();
    for entry in fs::read_dir(root_path).map_err(|e| format!("read scenario dir: {e}"))? {
        let entry = entry.map_err(|e| format!("read scenario entry: {e}"))?;
        let path = entry.path();
        if path
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|ext| ext == "json")
        {
            files.push(path);
        }
    }
    files.sort();

    let mut out = Vec::new();
    for file in files {
        let raw = fs::read_to_string(&file).map_err(|e| format!("read scenario file: {e}"))?;
        let parsed: ScenarioSpec =
            serde_json::from_str(&raw).map_err(|e| format!("parse scenario file: {e}"))?;
        out.push(parsed);
    }
    Ok(out)
}
