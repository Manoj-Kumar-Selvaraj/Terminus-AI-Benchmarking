use crate::model::types::{LaunchIx, RetryVec, VariantTag};
use crate::runtime::launcher::variant_merge::normalize_route_choice;

pub fn route_d1(ix: &LaunchIx, rv: &RetryVec) -> VariantTag {
    let take_alt = rv.retry_count > 0 && ix.prefer_alt;
    normalize_route_choice(ix.primary.clone(), ix.fallback.clone(), take_alt)
}
