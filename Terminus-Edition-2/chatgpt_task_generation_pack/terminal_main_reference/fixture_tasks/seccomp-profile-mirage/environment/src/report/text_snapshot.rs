use crate::model::types::ReportRow;

pub fn snapshot_line(row: &ReportRow) -> String {
    format!(
        "{}|{}|{}|{}",
        row.scenario, row.selected_tag, row.attached_tag, row.compliant
    )
}
