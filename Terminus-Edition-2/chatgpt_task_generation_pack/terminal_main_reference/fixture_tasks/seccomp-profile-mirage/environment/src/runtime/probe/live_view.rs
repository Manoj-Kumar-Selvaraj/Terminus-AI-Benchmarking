use crate::model::types::ScenarioSpec;

pub fn probe_for(spec: &ScenarioSpec, attached_tag: &str) -> bool {
    if attached_tag == spec.primary_tag {
        return spec.runtime_denies_primary;
    }
    if attached_tag == spec.fallback_tag {
        return spec.runtime_denies_fallback;
    }
    false
}
