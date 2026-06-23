use crate::model::types::RetryVec;

pub fn merge_retry(base: &RetryVec, extra: u32) -> RetryVec {
    RetryVec {
        retry_count: base.retry_count + extra.saturating_sub(base.retry_count),
    }
}
