//! Integration probes for routing/bind/gating; scenarios differ from bundled JSON fixtures.

use seccomp_profile_mirage::model::types::{AttachCtx, BindMemo, DocView, ProbeView, RunHist, ScenarioSpec};
use seccomp_profile_mirage::report::decision::gate_z8;
use seccomp_profile_mirage::runtime::attach::filter_bind::bind_k2;
use seccomp_profile_mirage::runtime::launcher::{
    retry_path::retry_vec_from, variant_select::route_d1, wrap_exec::launch_ix_from,
};

#[test]
fn routing_honors_retries_and_marker_flags() {
    let spec_take = ScenarioSpec {
        scenario: "inline_take".into(),
        primary_tag: "lane_a".into(),
        fallback_tag: "lane_b".into(),
        declared_tag: "lane_a".into(),
        retry_count: 4,
        prefer_alt: true,
        op_name: "unused".into(),
        declared_allows_op: false,
        runtime_denies_primary: true,
        runtime_denies_fallback: false,
    };
    let rv = retry_vec_from(&spec_take);
    let ix = launch_ix_from(&spec_take);
    assert_eq!(route_d1(&ix, &rv), "lane_b");

    let spec_hold = ScenarioSpec {
        retry_count: 0,
        prefer_alt: false,
        ..spec_take
    };
    let rv2 = retry_vec_from(&spec_hold);
    let ix2 = launch_ix_from(&spec_hold);
    assert_eq!(route_d1(&ix2, &rv2), "lane_a");
}

#[test]
fn routed_variant_surfaces_through_bind_even_if_declaration_differs() {
    let mut memo = BindMemo::default();
    let ctx = AttachCtx {
        scenario: "fixture_x".into(),
        declared_tag: "decl_blue".into(),
    };
    let ack = bind_k2(&ctx, "route_red".into(), &mut memo);
    assert_eq!(ack.attached_tag, "route_red");
}

#[test]
fn allowance_mismatch_must_not_be_reported_as_compliant() {
    let doc = DocView {
        scenario: "inline_op".into(),
        declared_tag: "tag_even".into(),
        declared_allows_op: true,
    };
    let live = ProbeView {
        scenario: "inline_op".into(),
        selected_tag: "tag_even".into(),
        attached_tag: "tag_even".into(),
        blocked: true,
    };
    let hist = RunHist { retry_count: 0 };
    let gate = gate_z8(&doc, &live, &hist);
    assert!(!gate.compliant);
    let low = gate.reason.to_lowercase();
    assert!(
        low.contains("drift"),
        "reason should cite drift wording: {}",
        gate.reason
    );
}
