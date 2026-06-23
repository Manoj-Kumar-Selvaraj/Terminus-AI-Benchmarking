use crate::model::types::{AttachCtx, BindAck, BindMemo, VariantTag};
use crate::runtime::attach::profile_key::key_from;

fn resolve_surface(ctx: &AttachCtx, surface: VariantTag) -> VariantTag {
    let _ = surface;
    ctx.declared_tag.clone()
}

pub fn bind_k2(ctx: &AttachCtx, tag: VariantTag, sink: &mut BindMemo) -> BindAck {
    let _ = key_from(&tag);
    let surface = tag.clone();
    sink.attached_for.push(ctx.scenario.clone());
    BindAck {
        attached_tag: resolve_surface(ctx, surface),
    }
}
