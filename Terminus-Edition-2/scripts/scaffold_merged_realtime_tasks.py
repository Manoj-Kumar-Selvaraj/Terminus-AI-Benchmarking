#!/usr/bin/env python3
"""Scaffold merged realtime reconciliation tasks (credit-matcher + window-settler) in Go and Ruby."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GO_TEMPLATE = ROOT / "go-port-terminal-container-hold-release"
RUBY_TEMPLATE = ROOT / "ruby-parking-garage-session-adjustment-clearing"

GO_BASE_IMAGE = (
    "FROM "
    "golang:1.22.12-bookworm@sha256:3d699e4d15d0f8f13c9195c0632a16702b8cbdece2955af1c23b37ae5d55a253"
)
RUBY_DIGEST = (
    "ruby:3.3.5-slim@sha256:25a9df53c6f23406f6bc87426ad5bd74b6d99423a8c2ca630f2443dee2447f53"
)

TEST_SH = """#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
pytest_status=1
trap 'exit $pytest_status' EXIT

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/{test_file} -rA
pytest_status=$?

if [ $pytest_status -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def apply_pairs(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in sorted(pairs, key=lambda x: len(x[0]), reverse=True):
        text = text.replace(old, new)
    return text


def go_hold_type_ok(milestone: int, spec: dict) -> str:
    cats = spec["cats_m1"] if milestone == 1 else spec["cats"]
    return "||".join(f's=="{c}"' for c in cats)


def go_reason_ok(spec: dict) -> str:
    return "||".join(f's=="{r}"' for r in spec["reasons"])


def go_solve_go(spec: dict, milestone: int) -> str:
    c0, c1, c2 = spec["cats"]
    a0, a1, a2 = (a for a, _ in spec["aliases"])
    hold_ok = go_hold_type_ok(milestone, spec)
    reason_ok = go_reason_ok(spec)
    sf = spec["source_file"]
    af = spec["action_file"]
    sid = spec["source_id_col"]
    party = spec["party_col"]
    scope = spec["scope_col"]
    loc = spec["loc_col"]
    cat = spec["category_col"]
    sts = spec["source_ts_col"]
    ats = spec["action_ts_col"]
    aid = spec["action_id_col"]
    wscope = spec["window_scope_col"]
    report = spec["report_file"]
    summary = spec["summary_file"]
    posted = spec["posted_status"]
    if milestone == 1:
        canon_fn = f'''func canon(s string) string{{switch strings.ToUpper(strings.TrimSpace(s)){{case "{a0}", "{c0}": return "{c0}"
case "{a1}", "{c1}": return "{c1}"
default: return strings.ToUpper(strings.TrimSpace(s))}}}}'''
    else:
        canon_fn = f'''func canon(s string) string{{switch strings.ToUpper(strings.TrimSpace(s)){{case "{a0}", "{c0}": return "{c0}"
case "{a1}", "{c1}": return "{c1}"
case "{a2}", "{c2}": return "{c2}"
default: return strings.ToUpper(strings.TrimSpace(s))}}}}'''

    return f'''package main
import("encoding/csv";"fmt";"os";"path/filepath";"strconv";"strings")
type rec struct{{id,party,scope,hold_type,amount,ts,status,loc string; used bool}}
type actrec struct{{aid,id,party,scope,hold_type,amount,ts,reason,loc string}}
type win struct{{scope,open,close,state string}}
func readCUV(p string) []map[string]string{{f,e:=os.Open(p); if e!=nil{{panic(e)}}; defer f.Close(); r:=csv.NewReader(f); rows,e:=r.ReadAll(); if e!=nil{{panic(e)}}; h:=rows[0]; out:=[]map[string]string{{}}; for _,row:=range rows[1:]{{m:=map[string]string{{}}; for i,k:=range h{{if i<len(row){{m[strings.TrimSpace(k)]=strings.TrimSpace(row[i])}}}}; out=append(out,m)}}; return out}}
func digits(s string) bool{{if len(s)!=14{{return false}}; for _,r:=range s{{if r<'0'||r>'9'{{return false}}}}; return true}}
{canon_fn}
func hold_typeOK(s string) bool{{return {hold_ok}}}
func reasonOK(s string) bool{{return {reason_ok}}}
func windowOK(src rec, act actrec, ws []win) bool{{if !digits(src.ts)||!digits(act.ts){{return false}}; for _,w:=range ws{{if w.scope==src.scope&&w.state=="OPEN"&&digits(w.open)&&digits(w.close)&&src.ts>=w.open&&src.ts<=w.close&&act.ts>=src.ts&&act.ts<=w.close{{return true}}}}; return false}}
func main(){{sources:=[]rec{{}}; for _,m:=range readCUV("/app/data/{sf}"){{sources=append(sources,rec{{m["{sid}"],m["{party}"],m["{scope}"],canon(m["{cat}"]),m["amount"],m["{sts}"],m["status"],m["{loc}"],false}})}}; actions:=[]actrec{{}}; for _,m:=range readCUV("/app/data/{af}"){{actions=append(actions,actrec{{m["{aid}"],m["{sid}"],m["{party}"],m["{scope}"],canon(m["{cat}"]),m["amount"],m["{ats}"],m["reason"],m["{loc}"]}})}}; windows:=[]win{{}}; for _,m:=range readCUV("/app/config/windows.csv"){{windows=append(windows,win{{m["{wscope}"],m["open_ts"],m["close_ts"],m["state"]}})}}; os.MkdirAll("/app/out",0755); f,_:=os.Create("/app/out/{report}"); defer f.Close(); w:=csv.NewWriter(f); defer w.Flush(); w.Write([]string{{"{aid}","{sid}","{party}","{scope}","{cat}","amount","reason","status"}}); mc,uc,ma,ua:=0,0,0,0; for _,act:=range actions{{hold_type:=act.hold_type; best := -1
		for i, src := range sources {{
			if src.id == act.id && src.amount == act.amount && !src.used && src.party == act.party && src.scope == act.scope && src.loc == act.loc && hold_typeOK(src.hold_type) && src.status == "{posted}" && src.hold_type == hold_type && reasonOK(act.reason) && windowOK(src, act, windows) {{
				if best < 0 || src.ts > sources[best].ts {{ best = i }}
			}}
		}}; amt,_:=strconv.Atoi(act.amount); if best>=0{{sources[best].used = true; mc++; ma+=amt; w.Write([]string{{act.aid,act.id,act.party,act.scope,sources[best].hold_type,act.amount,act.reason,"MATCHED"}})}}else{{uc++; ua+=amt; w.Write([]string{{act.aid,act.id,act.party,act.scope,"",act.amount,act.reason,"UNMATCHED"}})}}}}; os.WriteFile(filepath.Clean("/app/out/{summary}"),[]byte(fmt.Sprintf("matched_count=%d\\nmatched_amount=%d\\nunmatched_count=%d\\nunmatched_amount=%d\\n",mc,ma,uc,ua)),0644)}}'''


def go_solve_sh(spec: dict, milestone: int) -> str:
    body = go_solve_go(spec, milestone)
    return f'''#!/bin/bash
set -euo pipefail
cat > /app/cmd/reconcile/main.go <<'GO'
{body}
GO
/app/scripts/run_batch.sh
'''


def ruby_canon_fn(spec: dict, milestone: int) -> str:
    if milestone == 1:
        lines = ["  v.to_s.strip.upcase"]
    else:
        lines = []
        for alias, canon in spec["aliases"]:
            lines.append(f"  return '{canon}' if v == '{alias}' || v == '{canon}'")
        lines.append("  v.to_s.strip.upcase")
    return "\n".join(lines)


def ruby_rate_ok(spec: dict, milestone: int) -> str:
    cats = spec["cats_m1"] if milestone == 1 else spec["cats"]
    inner = ", ".join(f"'{c}'" for c in cats)
    return f"  [{inner}].include?(v)"


def ruby_solve_rb(spec: dict, milestone: int) -> str:
    reasons = ", ".join(f"'{r}'" for r in spec["reasons"])
    rate_ok = ruby_rate_ok(spec, milestone)
    canon_body = ruby_canon_fn(spec, milestone)
    sf = spec["source_file"]
    af = spec["action_file"]
    sid = spec["source_id_col"]
    party = spec["party_col"]
    scope = spec["scope_col"]
    loc = spec["loc_col"]
    cat = spec["category_col"]
    sts = spec["source_ts_col"]
    ats = spec["action_ts_col"]
    aid = spec["action_id_col"]
    wscope = spec["window_scope_col"]
    report = spec["report_file"]
    summary = spec["summary_file"]
    posted = spec["posted_status"]
    report_cols = f"{aid} {sid} {party} {scope} {cat} amount reason status"
    return f'''require 'csv'
require 'fileutils'

def canon(v)
{canon_body}
end

def digits?(v)
  v.to_s.match?(/\\A\\d{{14}}\\z/)
end

def rate_type_ok?(v)
{rate_ok}
end

def reason_ok?(v)
  [{reasons}].include?(v)
end

def window_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  windows.any? do |w|
    w[:scope] == src[:scope] &&
      w[:state] == 'OPEN' &&
      digits?(w[:open]) &&
      digits?(w[:close]) &&
      src[:ts] >= w[:open] &&
      src[:ts] <= w[:close] &&
      act[:ts] >= src[:ts] &&
      act[:ts] <= w[:close]
  end
end

sources = CSV.read('/app/data/{sf}', headers: true).map.with_index do |r, i|
  {{
    id: r['{sid}'].strip,
    party: r['{party}'].strip,
    scope: r['{scope}'].strip,
    rate_type: canon(r['{cat}']),
    amount: r['amount'].strip,
    ts: r['{sts}'].strip,
    status: r['status'].strip.upcase,
    loc: r['{loc}'].strip,
    row: i,
    used: false
  }}
end

actions = CSV.read('/app/data/{af}', headers: true).map do |r|
  {{
    aid: r['{aid}'].strip,
    id: r['{sid}'].strip,
    party: r['{party}'].strip,
    scope: r['{scope}'].strip,
    rate_type: canon(r['{cat}']),
    amount: r['amount'].strip,
    ts: r['{ats}'].strip,
    reason: r['reason'].strip.upcase,
    loc: r['{loc}'].strip
  }}
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {{
    scope: r['{wscope}'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip.upcase
  }}
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/{report}', 'w') do |csv|
  csv << %w[{report_cols}]
  actions.each do |act|
    candidates = []
    sources.each_with_index do |src, i|
      next if src[:used]
      next unless src[:id] == act[:id]
      next unless src[:party] == act[:party]
      next unless src[:scope] == act[:scope]
      next unless src[:loc] == act[:loc]
      next unless src[:amount] == act[:amount]
      next unless src[:status] == '{posted}'
      next unless rate_type_ok?(src[:rate_type])
      next unless src[:rate_type] == act[:rate_type]
      next unless reason_ok?(act[:reason])
      next unless window_ok?(src, act, windows)
      candidates << i
    end
    candidates.sort_by! {{ |i| [-sources[i][:ts].to_i, sources[i][:row]] }}
    best = candidates.first
    amt = act[:amount].to_i
    if best
      sources[best][:used] = true
      mc += 1
      ma += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:rate_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

File.write('/app/out/{summary}', <<~SUMMARY)
  matched_count=#{{mc}}
  matched_amount=#{{ma}}
  unmatched_count=#{{uc}}
  unmatched_amount=#{{ua}}
SUMMARY
'''


def ruby_solve_sh(spec: dict, milestone: int) -> str:
    rb = ruby_solve_rb(spec, milestone)
    return f'''#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
{rb}
RUBY
/app/scripts/run_batch.sh
'''


def go_broken_main(spec: dict) -> str:
    a0, a1, a2 = (a for a, _ in spec["aliases"])
    c0, c1, c2 = spec["cats"]
    reason_ok = go_reason_ok(spec)
    sf = spec["source_file"]
    af = spec["action_file"]
    sid = spec["source_id_col"]
    party = spec["party_col"]
    scope = spec["scope_col"]
    loc = spec["loc_col"]
    cat = spec["category_col"]
    sts = spec["source_ts_col"]
    ats = spec["action_ts_col"]
    aid = spec["action_id_col"]
    wscope = spec["window_scope_col"]
    report = spec["report_file"]
    summary = spec["summary_file"]
    return f'''package main
import("encoding/csv";"fmt";"os";"path/filepath";"strconv";"strings")
type rec struct{{id,party,scope,hold_type,amount,ts,status,loc string; used bool}}
type actrec struct{{aid,id,party,scope,hold_type,amount,ts,reason,loc string}}
type win struct{{scope,open,close,state string}}
func readCUV(p string) []map[string]string{{f,e:=os.Open(p); if e!=nil{{panic(e)}}; defer f.Close(); r:=csv.NewReader(f); rows,e:=r.ReadAll(); if e!=nil{{panic(e)}}; h:=rows[0]; out:=[]map[string]string{{}}; for _,row:=range rows[1:]{{m:=map[string]string{{}}; for i,k:=range h{{if i<len(row){{m[strings.TrimSpace(k)]=strings.TrimSpace(row[i])}}}}; out=append(out,m)}}; return out}}
func digits(s string) bool{{if len(s)!=14{{return false}}; for _,r:=range s{{if r<'0'||r>'9'{{return false}}}}; return true}}
func canon(s string) string{{switch strings.ToUpper(strings.TrimSpace(s)){{case "{a0}", "{c0}": return "{c0}"
case "{a1}", "{c1}": return "{c1}"
case "{a2}", "{c2}": return "{c2}"
default: return strings.ToUpper(strings.TrimSpace(s))}}}}
func reasonOK(s string) bool{{return {reason_ok}}}
func windowOK(src rec, act actrec, ws []win) bool{{if !digits(src.ts)||!digits(act.ts){{return false}}; for _,w:=range ws{{if w.scope==src.scope&&w.state=="OPEN"&&digits(w.open)&&digits(w.close)&&src.ts>=w.open&&src.ts<=w.close&&act.ts>=src.ts&&act.ts<=w.close{{return true}}}}; return false}}
func main(){{sources:=[]rec{{}}; for _,m:=range readCUV("/app/data/{sf}"){{sources=append(sources,rec{{m["{sid}"],m["{party}"],m["{scope}"],canon(m["{cat}"]),m["amount"],m["{sts}"],m["status"],m["{loc}"],false}})}}; actions:=[]actrec{{}}; for _,m:=range readCUV("/app/data/{af}"){{actions=append(actions,actrec{{m["{aid}"],m["{sid}"],m["{party}"],m["{scope}"],canon(m["{cat}"]),m["amount"],m["{ats}"],m["reason"],m["{loc}"]}})}}; windows:=[]win{{}}; for _,m:=range readCUV("/app/config/windows.csv"){{windows=append(windows,win{{m["{wscope}"],m["open_ts"],m["close_ts"],m["state"]}})}}; os.MkdirAll("/app/out",0755); f,_:=os.Create("/app/out/{report}"); defer f.Close(); w:=csv.NewWriter(f); defer w.Flush(); w.Write([]string{{"{aid}","{sid}","{party}","{scope}","{cat}","amount","reason","status"}}); mc,uc,ma,ua:=0,0,0,0; for _,act:=range actions{{hold_type:=act.hold_type; best := -1
		for i, src := range sources {{
			if (strings.HasPrefix(src.id, act.id) || strings.HasPrefix(act.id, src.id)) && src.amount == act.amount {{
				if best < 0 || src.ts > sources[best].ts {{ best = i }}
			}}
		}}; amt,_:=strconv.Atoi(act.amount); if best>=0{{mc++; ma-=amt; w.Write([]string{{act.aid,act.id,act.party,act.scope,sources[best].hold_type,act.amount,act.reason,"MATCHED"}})}}else{{uc++; ua+=amt; w.Write([]string{{act.aid,act.id,act.party,act.scope,"",act.amount,act.reason,"UNMATCHED"}})}}}}; os.WriteFile(filepath.Clean("/app/out/{summary}"),[]byte(fmt.Sprintf("matched_count=%d\\nmatched_amount=%d\\nunmatched_count=%d\\nunmatched_amount=%d\\n",mc,ma,uc,ua)),0644)}}'''


def ruby_broken_rb(spec: dict) -> str:
    sf = spec["source_file"]
    af = spec["action_file"]
    sid = spec["source_id_col"]
    party = spec["party_col"]
    scope = spec["scope_col"]
    loc = spec["loc_col"]
    cat = spec["category_col"]
    sts = spec["source_ts_col"]
    ats = spec["action_ts_col"]
    aid = spec["action_id_col"]
    report = spec["report_file"]
    summary = spec["summary_file"]
    report_cols = f"{aid} {sid} {party} {scope} {cat} amount reason status"
    return f'''require 'csv'
require 'fileutils'

def canon(v)
  v.to_s.strip.upcase
end

sources = CSV.read('/app/data/{sf}', headers: true).map.with_index do |r, i|
  {{
    id: r['{sid}'].strip,
    party: r['{party}'].strip,
    scope: r['{scope}'].strip,
    rate_type: canon(r['{cat}']),
    amount: r['amount'].strip,
    ts: r['{sts}'].strip,
    status: r['status'].strip,
    loc: r['{loc}'].strip,
    row: i,
    used: false
  }}
end

actions = CSV.read('/app/data/{af}', headers: true).map do |r|
  {{
    aid: r['{aid}'].strip,
    id: r['{sid}'].strip,
    party: r['{party}'].strip,
    scope: r['{scope}'].strip,
    rate_type: canon(r['{cat}']),
    amount: r['amount'].strip,
    ts: r['{ats}'].strip,
    reason: r['reason'].strip,
    loc: r['{loc}'].strip
  }}
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/{report}', 'w') do |csv|
  csv << %w[{report_cols}]
  actions.each do |act|
    best = nil
    sources.each_with_index do |src, i|
      next unless src[:id].start_with?(act[:id]) || act[:id].start_with?(src[:id])
      next unless src[:amount] == act[:amount]
      best = i
      break
    end
    amt = act[:amount].to_i
    if best
      mc += 1
      ma -= amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], sources[best][:rate_type], act[:amount], act[:reason], 'MATCHED']
    else
      uc += 1
      ua += amt
      csv << [act[:aid], act[:id], act[:party], act[:scope], '', act[:amount], act[:reason], 'UNMATCHED']
    end
  end
end

File.write('/app/out/{summary}', <<~SUMMARY)
  matched_count=#{{mc}}
  matched_amount=#{{ma}}
  unmatched_count=#{{uc}}
  unmatched_amount=#{{ua}}
SUMMARY
'''


def build_go_pairs(spec: dict) -> list[tuple[str, str]]:
    slug = spec["slug"]
    old = "go-port-terminal-container-hold-release"
    c0, c1, c2 = spec["cats"]
    r0, r1, r2 = spec["reasons"]
    pairs = [
        (old, slug),
        ("port terminal container hold-release", spec["title"]),
        ("port terminal container hold release", spec["title_short"]),
        ("holds.csv", spec["source_file"]),
        ("releases.csv", spec["action_file"]),
        ("hold_id", spec["source_id_col"]),
        ("container_id", spec["party_col"]),
        ("gate_id", spec["scope_col"]),
        ("lane", spec["loc_col"]),
        ("hold_type", spec["category_col"]),
        ("hold_ts", spec["source_ts_col"]),
        ("release_ts", spec["action_ts_col"]),
        ("release_id", spec["action_id_col"]),
        ("release_report.csv", spec["report_file"]),
        ("release_summary.txt", spec["summary_file"]),
        ("INSPECTION", c0),
        ("CUSTOMS", c1),
        ("SECURITY", c2),
        ("CLINRED", r0),
        ("WAIVED", r1),
        ("OVERRIDE", r2),
        ("ACTIVE", spec["posted_status"]),
    ]
    return pairs


def build_ruby_pairs(spec: dict) -> list[tuple[str, str]]:
    slug = spec["slug"]
    old = "ruby-parking-garage-session-adjustment-clearing"
    c0, c1, c2 = spec["cats"]
    r0, r1, r2 = spec["reasons"]
    pairs = [
        (old, slug),
        ("parking garage session adjustment", spec["title"]),
        ("courier COD remittance", spec["title_short"]),
        ("sessions.csv", spec["source_file"]),
        ("adjustments.csv", spec["action_file"]),
        ("parcel_id", spec["source_id_col"]),
        ("plate_id", spec["party_col"]),
        ("station_id", spec["scope_col"]),
        ("level", spec["loc_col"]),
        ("rate_type", spec["category_col"]),
        ("entry_ts", spec["source_ts_col"]),
        ("adjust_ts", spec["action_ts_col"]),
        ("adjustment_id", spec["action_id_col"]),
        ("cod_parking_adjustment_report.csv", spec["report_file"]),
        ("cod_parking_adjustment_summary.txt", spec["summary_file"]),
        ("HOURLY", c0),
        ("DAILY", c1),
        ("EVENT", c2),
        ("REFUND", r0),
        ("SHORT", r1),
        ("WAIVE", r2),
        ("CLOSED", spec["posted_status"]),
    ]
    return pairs


def rubric_for(spec: dict) -> str:
    col = spec["category_col"]
    slug = spec["slug"]
    m1_cats = " or ".join(f"`{c}`" for c in spec["cats_m1"])
    all_cats = ", ".join(f"`{c}`" for c in spec["cats"])
    alias_text = ", ".join(f"`{a}` means `{c}`" for a, c in spec["aliases"])
    return f"""Agent investigates and updates intended `{slug}` implementation paths (/app/data/{spec['source_file']}, /app/data/{spec['action_file']}, /app/config/windows.csv) instead of unrelated files, +2
Agent satisfies `{slug}` milestone 1 core requirement: Preserve action input order, write the documented report schema, use `MATCHED` or `UNMATCHED` only, leave the canonical {col} field blank for unmatched rows, and write positive matched and unmatched summary totals, +5
Agent preserves milestone 1 rule for `{slug}`: A correction can match only when the full source identifier and all identity fields match, the amount matches as an integer value, the source status uses the documented eligible literal, and the correction reason is allowed, +3
Agent handles milestone 1 edge and consumption behavior for `{slug}` validated by tests, +3
Agent satisfies `{slug}` milestone 2 core requirement: Normalize aliases after trimming and case folding before matching and emit only canonical {col} values in matched report rows, +5
Agent preserves milestone 2 rule for `{slug}`: Milestone 2 keeps every milestone 1 rule and adds legacy {col} aliases ({alias_text}), +3
Agent handles milestone 2 alias edge behavior for `{slug}` validated by tests, +3
Agent satisfies `{slug}` milestone 3 core requirement: The realtime window file is authoritative for OPEN windows, timestamp ordering, latest-source tie-breaks, and row-position consumption, +5
Agent preserves milestone 3 rule for `{slug}`: {col.title()} aliases remain normalized and canonical gates for {all_cats} still apply, +3
Agent handles milestone 3 window edge behavior for `{slug}` validated by tests, +3
Agent validates `{slug}` output artifacts against required schemas and deterministic ordering before finalizing, +3
Agent treats only canonical {col} values {m1_cats} as match-eligible in milestone 1 and leaves unknown {col} values unmatched, +3
Agent treats only canonical {col} values {all_cats} as match-eligible from milestone 2 onward, +3
Agent hardcodes final output files for `{slug}` instead of fixing underlying implementation, -5
Agent tampers with verifier harness files, solution scaffolding, or input fixtures in `{slug}` to force a pass, -5
Agent regresses earlier milestones in `{slug}` while implementing later milestone changes, -3
Agent repeats failing commands for `{slug}` without adjusting approach after clear errors, -2
"""


def patch_instructions(dest: Path, spec: dict) -> None:
    a0, a1, a2 = (a for a, _ in spec["aliases"])
    c0, c1, c2 = spec["cats"]
    for path in dest.glob("steps/milestone_*/instruction.md"):
        text = path.read_text(encoding="utf-8")
        for old, new in (
            ("`IN` means `INSPECTION`", f"`{a0}` means `{c0}`"),
            ("`CU` means `CUSTOMS`", f"`{a1}` means `{c1}`"),
            ("`SE` means `SECURITY`", f"`{a2}` means `{c2}`"),
            ("`HR` means `HOURLY`", f"`{a0}` means `{c0}`"),
            ("`QR` means `DAILY`", f"`{a1}` means `{c1}`"),
            ("`CC` means `EVENT`", f"`{a2}` means `{c2}`"),
            ("Hold_Type aliases", f"{spec['category_col'].title()} aliases"),
            ("Rate_Type aliases", f"{spec['category_col'].title()} aliases"),
            ("hold_type", spec["category_col"]),
            ("rate_type", spec["category_col"]),
        ):
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def patch_go_tests(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    c0, c1, c2 = spec["cats"]
    a0, a1, a2 = (a for a, _ in spec["aliases"])
    r0, r1, r2 = spec["reasons"]
    for old, new in (
        ("INSPECTION", c0),
        ("CUSTOMS", c1),
        ("SECURITY", c2),
        ("CLINRED", r0),
        ("WAIVED", r1),
        ("OVERRIDE", r2),
        (",IN,", f",{a0},"),
        (",CU,", f",{a1},"),
        (",SE,", f",{a2},"),
        ("Legacy IN", f"Legacy {a0}"),
        ("The IN alias", f"The {a0} alias"),
    ):
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def patch_ruby_tests(path: Path, spec: dict) -> None:
    text = path.read_text(encoding="utf-8")
    c0, c1, c2 = spec["cats"]
    a0, a1, a2 = (a for a, _ in spec["aliases"])
    for old, new in (
        ("HOURLY", c0),
        ("DAILY", c1),
        ("EVENT", c2),
        (",HR,", f",{a0},"),
        (",QR,", f",{a1},"),
        (",CC,", f",{a2},"),
        ("Legacy HR", f"Legacy {a0}"),
        ("The HR alias", f"The {a0} alias"),
    ):
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def finalize_solves(dest: Path, spec: dict, lang: str) -> None:
    solves = {
        n: (go_solve_sh(spec, n) if lang == "go" else ruby_solve_sh(spec, n))
        for n in (1, 2, 3)
    }
    for milestone in (1, 2, 3):
        mdir = dest / "steps" / f"milestone_{milestone}" / "solution"
        for n in range(1, milestone + 1):
            write_lf(mdir / f"solve{n}.sh", solves[n])
        wrapper = f"""#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
bash "$SCRIPT_DIR/solve{milestone}.sh"
"""
        write_lf(mdir / "solve.sh", wrapper)


def scaffold_go(spec: dict) -> None:
    dest = ROOT / spec["slug"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(GO_TEMPLATE, dest)
    pairs = build_go_pairs(spec)
    for path in dest.rglob("*"):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        if ".pytest_cache" in path.parts:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        path.write_text(apply_pairs(content, pairs), encoding="utf-8")

    write_lf(dest / "environment/cmd/reconcile/main.go", go_broken_main(spec))
    finalize_solves(dest, spec, "go")
    for milestone in (1, 2, 3):
        patch_go_tests(dest / f"steps/milestone_{milestone}/tests/test_m{milestone}.py", spec)
        write_lf(dest / f"steps/milestone_{milestone}/tests/test.sh", TEST_SH.format(test_file=f"test_m{milestone}.py"))

    dockerfile = dest / "environment/Dockerfile"
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    if lines:
        lines[0] = GO_BASE_IMAGE
        dockerfile.write_text("\n".join(lines) + "\n", encoding="utf-8")

    toml = dest / "task.toml"
    t = toml.read_text(encoding="utf-8")
    t = re.sub(r'tags = \[.*?\]', f'tags = ["go", "csv", "realtime", "{spec["tag"]}", "reconciliation"]', t)
    t = re.sub(r'languages = \[.*?\]', 'languages = ["go"]', t)
    toml.write_text(t, encoding="utf-8")
    write_lf(dest / "rubric.txt", rubric_for(spec))
    patch_instructions(dest, spec)
    for sh in dest.rglob("*.sh"):
        write_lf(sh, sh.read_text(encoding="utf-8"))
    print(f"created {spec['slug']}")


def scaffold_ruby(spec: dict) -> None:
    dest = ROOT / spec["slug"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(RUBY_TEMPLATE, dest)
    pairs = build_ruby_pairs(spec)
    for path in dest.rglob("*"):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        if ".pytest_cache" in path.parts:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        path.write_text(apply_pairs(content, pairs), encoding="utf-8")

    write_lf(dest / "environment/app/reconcile.rb", ruby_broken_rb(spec))
    finalize_solves(dest, spec, "ruby")
    for milestone in (1, 2, 3):
        patch_ruby_tests(dest / f"steps/milestone_{milestone}/tests/test_m{milestone}.py", spec)
        write_lf(dest / f"steps/milestone_{milestone}/tests/test.sh", TEST_SH.format(test_file=f"test_m{milestone}.py"))

    dockerfile = dest / "environment/Dockerfile"
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    if lines:
        lines[0] = f"FROM {RUBY_DIGEST}"
        dockerfile.write_text("\n".join(lines) + "\n", encoding="utf-8")

    toml = dest / "task.toml"
    t = toml.read_text(encoding="utf-8")
    t = re.sub(r'tags = \[.*?\]', f'tags = ["ruby", "csv", "realtime", "{spec["tag"]}", "reconciliation"]', t)
    t = re.sub(r'languages = \[.*?\]', 'languages = ["ruby"]', t)
    toml.write_text(t, encoding="utf-8")
    write_lf(dest / "rubric.txt", rubric_for(spec))
    patch_instructions(dest, spec)
    for sh in dest.rglob("*.sh"):
        write_lf(sh, sh.read_text(encoding="utf-8"))
    print(f"created {spec['slug']}")


TASKS = [
    {
        "slug": "go-airport-gate-baggage-hold-release",
        "lang": "go",
        "tag": "airport",
        "title": "airport gate baggage hold release",
        "title_short": "airport gate baggage hold release",
        "source_file": "holds.csv",
        "action_file": "releases.csv",
        "source_id_col": "hold_id",
        "party_col": "bag_tag_id",
        "scope_col": "gate_id",
        "loc_col": "carousel",
        "category_col": "check_type",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "gate_id",
        "report_file": "baggage_release_report.csv",
        "summary_file": "baggage_release_summary.txt",
        "posted_status": "ACTIVE",
        "reasons": ["CLEAR", "MEDICAL", "OVERRIDE"],
        "cats_m1": ["SECURITY", "CUSTOMS"],
        "cats": ["SECURITY", "CUSTOMS", "MEDICAL"],
        "aliases": [("SC", "SECURITY"), ("CU", "CUSTOMS"), ("MD", "MEDICAL")],
    },
    {
        "slug": "go-rail-yard-freight-hold-release",
        "lang": "go",
        "tag": "rail-yard",
        "title": "rail yard freight hold release",
        "title_short": "rail yard freight hold release",
        "source_file": "holds.csv",
        "action_file": "releases.csv",
        "source_id_col": "hold_id",
        "party_col": "car_id",
        "scope_col": "yard_id",
        "loc_col": "track",
        "category_col": "cargo_class",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "yard_id",
        "report_file": "freight_release_report.csv",
        "summary_file": "freight_release_summary.txt",
        "posted_status": "HELD",
        "reasons": ["RELEASE", "RECALL", "OVERRIDE"],
        "cats_m1": ["HAZ", "DRY"],
        "cats": ["HAZ", "DRY", "REF"],
        "aliases": [("HZ", "HAZ"), ("DR", "DRY"), ("RF", "REF")],
    },
    {
        "slug": "go-datacenter-rack-hold-release",
        "lang": "go",
        "tag": "datacenter",
        "title": "datacenter rack hold release",
        "title_short": "datacenter rack hold release",
        "source_file": "holds.csv",
        "action_file": "releases.csv",
        "source_id_col": "hold_id",
        "party_col": "asset_id",
        "scope_col": "aisle_id",
        "loc_col": "rack",
        "category_col": "access_tier",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "aisle_id",
        "report_file": "rack_release_report.csv",
        "summary_file": "rack_release_summary.txt",
        "posted_status": "LOCKED",
        "reasons": ["DECOMM", "MIGRATE", "OVERRIDE"],
        "cats_m1": ["HOT", "WARM"],
        "cats": ["HOT", "WARM", "COLD"],
        "aliases": [("HT", "HOT"), ("WM", "WARM"), ("CL", "COLD")],
    },
    {
        "slug": "go-coldchain-pallet-hold-release",
        "lang": "go",
        "tag": "coldchain",
        "title": "cold chain pallet hold release",
        "title_short": "cold chain pallet hold release",
        "source_file": "holds.csv",
        "action_file": "releases.csv",
        "source_id_col": "hold_id",
        "party_col": "pallet_id",
        "scope_col": "zone_id",
        "loc_col": "bay",
        "category_col": "temp_band",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "zone_id",
        "report_file": "pallet_release_report.csv",
        "summary_file": "pallet_release_summary.txt",
        "posted_status": "QUARANTINED",
        "reasons": ["SPOIL", "QUAR", "OVERRIDE"],
        "cats_m1": ["FROZEN", "CHILL"],
        "cats": ["FROZEN", "CHILL", "AMBIENT"],
        "aliases": [("FZ", "FROZEN"), ("CH", "CHILL"), ("AM", "AMBIENT")],
    },
    {
        "slug": "ruby-ski-resort-lift-gate-release",
        "lang": "ruby",
        "tag": "ski-resort",
        "title": "ski resort lift gate release",
        "title_short": "ski resort lift gate release",
        "source_file": "lift_sessions.csv",
        "action_file": "gate_releases.csv",
        "source_id_col": "pass_id",
        "party_col": "skier_id",
        "scope_col": "lift_id",
        "loc_col": "slope",
        "category_col": "pass_tier",
        "source_ts_col": "scan_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "lift_id",
        "report_file": "lift_gate_release_report.csv",
        "summary_file": "lift_gate_release_summary.txt",
        "posted_status": "SCANNED",
        "reasons": ["VOID", "COMP", "GUEST"],
        "cats_m1": ["DAY", "SEASON"],
        "cats": ["DAY", "SEASON", "VIP"],
        "aliases": [("DY", "DAY"), ("SN", "SEASON"), ("VP", "VIP")],
    },
    {
        "slug": "ruby-marina-berth-hold-release",
        "lang": "ruby",
        "tag": "marina",
        "title": "marina berth hold release",
        "title_short": "marina berth hold release",
        "source_file": "berth_holds.csv",
        "action_file": "berth_releases.csv",
        "source_id_col": "hold_id",
        "party_col": "vessel_id",
        "scope_col": "dock_id",
        "loc_col": "slip",
        "category_col": "berth_type",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "dock_id",
        "report_file": "berth_release_report.csv",
        "summary_file": "berth_release_summary.txt",
        "posted_status": "MOORED",
        "reasons": ["DEPART", "TRANSFER", "OVERRIDE"],
        "cats_m1": ["SLIP", "DRY"],
        "cats": ["SLIP", "DRY", "TRANSIT"],
        "aliases": [("SL", "SLIP"), ("DR", "DRY"), ("TR", "TRANSIT")],
    },
    {
        "slug": "ruby-hospital-bed-hold-release",
        "lang": "ruby",
        "tag": "hospital",
        "title": "hospital bed hold release",
        "title_short": "hospital bed hold release",
        "source_file": "bed_holds.csv",
        "action_file": "bed_releases.csv",
        "source_id_col": "hold_id",
        "party_col": "patient_id",
        "scope_col": "ward_id",
        "loc_col": "room",
        "category_col": "care_level",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "ward_id",
        "report_file": "bed_release_report.csv",
        "summary_file": "bed_release_summary.txt",
        "posted_status": "OCCUPIED",
        "reasons": ["DISCH", "TRANS", "OVERRIDE"],
        "cats_m1": ["ACUTE", "OBS"],
        "cats": ["ACUTE", "OBS", "ICU"],
        "aliases": [("AC", "ACUTE"), ("OB", "OBS"), ("IC", "ICU")],
    },
    {
        "slug": "ruby-warehouse-dock-hold-release",
        "lang": "ruby",
        "tag": "warehouse",
        "title": "warehouse dock hold release",
        "title_short": "warehouse dock hold release",
        "source_file": "dock_holds.csv",
        "action_file": "dock_releases.csv",
        "source_id_col": "hold_id",
        "party_col": "shipment_id",
        "scope_col": "dock_id",
        "loc_col": "door",
        "category_col": "load_type",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "dock_id",
        "report_file": "dock_release_report.csv",
        "summary_file": "dock_release_summary.txt",
        "posted_status": "STAGED",
        "reasons": ["SHIP", "SHORT", "OVERRIDE"],
        "cats_m1": ["LTL", "FTL"],
        "cats": ["LTL", "FTL", "PARCEL"],
        "aliases": [("LT", "LTL"), ("FT", "FTL"), ("PK", "PARCEL")],
    },
    {
        "slug": "ruby-ev-charging-session-release",
        "lang": "ruby",
        "tag": "ev-charging",
        "title": "EV charging session release",
        "title_short": "EV charging session release",
        "source_file": "charge_sessions.csv",
        "action_file": "session_releases.csv",
        "source_id_col": "session_id",
        "party_col": "vehicle_id",
        "scope_col": "station_id",
        "loc_col": "port",
        "category_col": "rate_plan",
        "source_ts_col": "plug_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "station_id",
        "report_file": "ev_release_report.csv",
        "summary_file": "ev_release_summary.txt",
        "posted_status": "ACTIVE",
        "reasons": ["STOP", "FAULT", "OVERRIDE"],
        "cats_m1": ["LEVEL2", "DCFC"],
        "cats": ["LEVEL2", "DCFC", "FLEET"],
        "aliases": [("L2", "LEVEL2"), ("DC", "DCFC"), ("FL", "FLEET")],
    },
    {
        "slug": "ruby-laundry-locker-hold-release",
        "lang": "ruby",
        "tag": "laundry",
        "title": "laundry locker hold release",
        "title_short": "laundry locker hold release",
        "source_file": "locker_holds.csv",
        "action_file": "locker_releases.csv",
        "source_id_col": "hold_id",
        "party_col": "customer_id",
        "scope_col": "site_id",
        "loc_col": "locker",
        "category_col": "service_tier",
        "source_ts_col": "hold_ts",
        "action_ts_col": "release_ts",
        "action_id_col": "release_id",
        "window_scope_col": "site_id",
        "report_file": "locker_release_report.csv",
        "summary_file": "locker_release_summary.txt",
        "posted_status": "LOADED",
        "reasons": ["PICKUP", "REFUND", "OVERRIDE"],
        "cats_m1": ["WASH", "DRY"],
        "cats": ["WASH", "DRY", "COMBO"],
        "aliases": [("WS", "WASH"), ("DR", "DRY"), ("CB", "COMBO")],
    },
]


def main() -> None:
    for spec in TASKS:
        if spec["lang"] == "go":
            scaffold_go(spec)
        else:
            scaffold_ruby(spec)


if __name__ == "__main__":
    main()
