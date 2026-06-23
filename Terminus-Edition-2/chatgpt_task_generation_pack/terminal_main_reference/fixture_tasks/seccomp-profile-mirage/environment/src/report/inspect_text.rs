use crate::model::types::DocView;

pub fn digest_doc(doc: &DocView) -> String {
    format!(
        "{}:{}:{}",
        doc.scenario, doc.declared_tag, doc.declared_allows_op
    )
}
