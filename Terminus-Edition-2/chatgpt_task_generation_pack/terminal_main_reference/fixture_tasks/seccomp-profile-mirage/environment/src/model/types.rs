use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize)]
pub struct ScenarioSpec {
    pub scenario: String,
    pub primary_tag: String,
    pub fallback_tag: String,
    pub declared_tag: String,
    pub retry_count: u32,
    pub prefer_alt: bool,
    pub op_name: String,
    pub declared_allows_op: bool,
    pub runtime_denies_primary: bool,
    pub runtime_denies_fallback: bool,
}

#[derive(Clone, Debug)]
pub struct LaunchIx {
    pub primary: String,
    pub fallback: String,
    pub prefer_alt: bool,
}

#[derive(Clone, Debug)]
pub struct RetryVec {
    pub retry_count: u32,
}

#[derive(Clone, Debug)]
pub struct AttachCtx {
    pub scenario: String,
    pub declared_tag: String,
}

#[derive(Clone, Debug, Default)]
pub struct BindMemo {
    pub attached_for: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct BindAck {
    pub attached_tag: String,
}

#[derive(Clone, Debug)]
pub struct DocView {
    pub scenario: String,
    pub declared_tag: String,
    pub declared_allows_op: bool,
}

#[derive(Clone, Debug)]
pub struct ProbeView {
    pub scenario: String,
    pub selected_tag: String,
    pub attached_tag: String,
    pub blocked: bool,
}

#[derive(Clone, Debug)]
pub struct RunHist {
    pub retry_count: u32,
}

#[derive(Clone, Debug)]
pub struct ReportGate {
    pub compliant: bool,
    pub reason: String,
}

pub type VariantTag = String;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReportRow {
    pub scenario: String,
    pub selected_tag: String,
    pub attached_tag: String,
    pub declared_tag: String,
    pub declared_allows_op: bool,
    pub effective_blocked_op: bool,
    pub compliant: bool,
    pub reason: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Summary {
    pub compliant_count: usize,
    pub total: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AppReport {
    pub run_report: Vec<ReportRow>,
    pub summary: Summary,
}

#[derive(Clone, Debug)]
pub struct RuntimeConfig {
    pub scenario_root: String,
    pub output_file: String,
}
