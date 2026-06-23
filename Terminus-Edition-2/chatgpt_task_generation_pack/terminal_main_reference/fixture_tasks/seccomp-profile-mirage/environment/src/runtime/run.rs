use crate::model::types::{
    AppReport, AttachCtx, BindMemo, DocView, LaunchIx, ProbeView, ReportRow, RunHist,
    ScenarioSpec, Summary,
};
use crate::report::compose;
use crate::runtime::attach::filter_bind::bind_k2;
use crate::runtime::launcher::retry_path::retry_vec_from;
use crate::runtime::launcher::variant_cache::cache_variant;
use crate::runtime::launcher::variant_select::route_d1;
use crate::runtime::launcher::wrap_exec::launch_ix_from;
use crate::runtime::probe::live_view::probe_for;
use crate::runtime::session::rebind_state::merge_retry;

pub fn execute_scenarios(items: &[ScenarioSpec]) -> Result<AppReport, String> {
    let mut rows = Vec::new();
    let mut memo = BindMemo::default();
    for item in items {
        let mut rv = retry_vec_from(item);
        rv = merge_retry(&rv, item.retry_count);
        let ix: LaunchIx = launch_ix_from(item);
        let selected = route_d1(&ix, &rv);
        cache_variant(&item.scenario, &selected);

        let ctx = AttachCtx {
            scenario: item.scenario.clone(),
            declared_tag: item.declared_tag.clone(),
        };
        let ack = bind_k2(&ctx, selected.clone(), &mut memo);
        let blocked = probe_for(item, &ack.attached_tag);
        let live = ProbeView {
            scenario: item.scenario.clone(),
            selected_tag: selected.clone(),
            attached_tag: ack.attached_tag.clone(),
            blocked,
        };
        let doc = DocView {
            scenario: item.scenario.clone(),
            declared_tag: item.declared_tag.clone(),
            declared_allows_op: item.declared_allows_op,
        };
        let hist = RunHist {
            retry_count: item.retry_count,
        };
        let gate = compose::evaluate_gate(&doc, &live, &hist);
        rows.push(ReportRow {
            scenario: item.scenario.clone(),
            selected_tag: selected,
            attached_tag: ack.attached_tag,
            declared_tag: item.declared_tag.clone(),
            declared_allows_op: item.declared_allows_op,
            effective_blocked_op: blocked,
            compliant: gate.compliant,
            reason: gate.reason,
        });
    }
    rows.sort_by(|a, b| a.scenario.cmp(&b.scenario));
    let compliant_count = rows.iter().filter(|r| r.compliant).count();
    let report = AppReport {
        run_report: rows,
        summary: Summary {
            compliant_count,
            total: items.len(),
        },
    };
    Ok(compose::finalize(report))
}
