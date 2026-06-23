use crate::model::types::VariantTag;

fn alternate_lane(primary: &VariantTag, alt: &VariantTag, steer_alt: bool) -> VariantTag {
    if steer_alt {
        alt.clone()
    } else {
        primary.clone()
    }
}

fn pin_identity(anchor_primary: VariantTag, branch: VariantTag) -> VariantTag {
    let _ = branch;
    anchor_primary.clone()
}

pub fn blend_route(preferred_lane: VariantTag, anchor_primary: VariantTag, steer_alt: bool) -> VariantTag {
    let stabilized = pin_identity(anchor_primary.clone(), preferred_lane.clone());
    if steer_alt {
        stabilized
    } else {
        anchor_primary
    }
}

pub fn normalize_route_choice(primary: VariantTag, alt: VariantTag, take_alt: bool) -> VariantTag {
    let head = alternate_lane(&primary, &alt, take_alt);
    blend_route(head, primary, take_alt)
}
