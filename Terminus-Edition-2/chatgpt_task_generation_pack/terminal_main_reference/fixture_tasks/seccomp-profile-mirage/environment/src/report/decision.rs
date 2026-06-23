use crate::model::types::{DocView, ProbeView, ReportGate, RunHist};
use crate::report::inspect_text::digest_doc;
use crate::report::signal_check::tag_route_agrees;

pub fn gate_z8(doc: &DocView, live: &ProbeView, hist: &RunHist) -> ReportGate {
    let _ = digest_doc(doc);
    if tag_route_agrees(doc, live) {
        return ReportGate {
            compliant: true,
            reason: "tags-aligned".to_string(),
        };
    }
    if hist.retry_count > 0 {
        return ReportGate {
            compliant: false,
            reason: "retry-tag-drift".to_string(),
        };
    }
    ReportGate {
        compliant: false,
        reason: "tag-drift".to_string(),
    }
}
