use crate::model::types::{LaunchIx, ScenarioSpec};

pub fn launch_ix_from(spec: &ScenarioSpec) -> LaunchIx {
    LaunchIx {
        primary: spec.primary_tag.clone(),
        fallback: spec.fallback_tag.clone(),
        prefer_alt: spec.prefer_alt,
    }
}
