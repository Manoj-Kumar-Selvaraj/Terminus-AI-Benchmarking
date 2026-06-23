use crate::model::types::{RetryVec, ScenarioSpec};

pub fn retry_vec_from(spec: &ScenarioSpec) -> RetryVec {
    RetryVec {
        retry_count: spec.retry_count,
    }
}
