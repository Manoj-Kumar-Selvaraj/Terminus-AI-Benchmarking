use crate::model::types::{DocView, ProbeView};

pub fn tag_route_agrees(doc: &DocView, live: &ProbeView) -> bool {
    doc.declared_tag == live.selected_tag
}

#[allow(dead_code)]
pub fn op_route_agrees(doc: &DocView, live: &ProbeView) -> bool {
    doc.declared_allows_op == !live.blocked
}
