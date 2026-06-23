use crate::model::types::{AppReport, DocView, ProbeView, ReportGate, RunHist};
use crate::report::decision::gate_z8;
use crate::report::text_snapshot::snapshot_line;

pub fn evaluate_gate(doc: &DocView, live: &ProbeView, hist: &RunHist) -> ReportGate {
    gate_z8(doc, live, hist)
}

pub fn finalize(report: AppReport) -> AppReport {
    for row in &report.run_report {
        let _ = snapshot_line(row);
    }
    report
}
