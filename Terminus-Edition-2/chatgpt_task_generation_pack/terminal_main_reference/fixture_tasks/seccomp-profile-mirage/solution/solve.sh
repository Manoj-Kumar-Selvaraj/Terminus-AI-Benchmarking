#!/bin/bash
set -euo pipefail

cd /app
export PATH="/usr/local/cargo/bin:${PATH}"

cat > /app/src/runtime/launcher/variant_merge.rs <<'EOF'
use crate::model::types::VariantTag;

pub fn normalize_route_choice(primary: VariantTag, alt: VariantTag, take_alt: bool) -> VariantTag {
    if take_alt {
        alt
    } else {
        primary
    }
}
EOF

cat > /app/src/runtime/attach/filter_bind.rs <<'EOF'
use crate::model::types::{AttachCtx, BindAck, BindMemo, VariantTag};
use crate::runtime::attach::profile_key::key_from;

fn resolve_surface(_ctx: &AttachCtx, surface: VariantTag) -> VariantTag {
    surface
}

pub fn bind_k2(ctx: &AttachCtx, tag: VariantTag, sink: &mut BindMemo) -> BindAck {
    let _ = key_from(&tag);
    let surface = tag.clone();
    sink.attached_for.push(ctx.scenario.clone());
    BindAck {
        attached_tag: resolve_surface(ctx, surface),
    }
}
EOF

cat > /app/src/report/signal_check.rs <<'EOF'
use crate::model::types::{DocView, ProbeView};

pub fn tag_route_agrees(doc: &DocView, live: &ProbeView) -> bool {
    doc.declared_tag == live.attached_tag
}

pub fn op_route_agrees(doc: &DocView, live: &ProbeView) -> bool {
    doc.declared_allows_op == !live.blocked
}
EOF

cat > /app/src/report/decision.rs <<'EOF'
use crate::model::types::{DocView, ProbeView, ReportGate, RunHist};
use crate::report::inspect_text::digest_doc;
use crate::report::signal_check::{op_route_agrees, tag_route_agrees};

fn reason_tail(hist: &RunHist) -> String {
    if hist.retry_count == 0 {
        return "r0".to_string();
    }
    format!("r{}", hist.retry_count)
}

pub fn gate_z8(doc: &DocView, live: &ProbeView, hist: &RunHist) -> ReportGate {
    let _ = digest_doc(doc);
    let attached_matches = tag_route_agrees(doc, live);
    let allowance_matches = op_route_agrees(doc, live);
    let suffix = reason_tail(hist);
    if attached_matches && allowance_matches {
        return ReportGate {
            compliant: true,
            reason: "aligned".to_string(),
        };
    }
    if !attached_matches && !allowance_matches {
        return ReportGate {
            compliant: false,
            reason: format!("tag-and-allowance-drift:{suffix}"),
        };
    }
    if !attached_matches {
        return ReportGate {
            compliant: false,
            reason: format!("tag-drift:{suffix}"),
        };
    }
    ReportGate {
        compliant: false,
        reason: format!("allowance-drift:{suffix}"),
    }
}
EOF

cargo run --quiet --locked
