#!/usr/bin/env python3
"""Fix oracle failures for tasks listed in new_tasks.txt."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COBOL_TASKS = [
    {
        "slug": "cobol-bowling-league-fee-reversal",
        "data": [("dock_fees.dat", "lane_fees.dat")],
        "config": [("harbor_calendar.txt", "league_calendar.txt")],
    },
    {
        "slug": "cobol-campground-site-deposit-matcher",
        "data": [
            ("dock_fees.dat", "site_fees.dat"),
            ("reversals.dat", "deposit_returns.dat"),
        ],
        "config": [("harbor_calendar.txt", "season_calendar.txt")],
    },
    {
        "slug": "cobol-laundromat-load-credit-clearing",
        "data": [
            ("dock_fees.dat", "machine_loads.dat"),
            ("reversals.dat", "credits.dat"),
        ],
        "config": [("harbor_calendar.txt", "service_calendar.txt")],
    },
    {
        "slug": "cobol-scooter-ride-surcharge-reversal",
        "data": [
            ("dock_fees.dat", "ride_charges.dat"),
            ("reversals.dat", "surcharge_reversals.dat"),
        ],
        "config": [("harbor_calendar.txt", "fleet_calendar.txt")],
    },
    {
        "slug": "cobol-zoo-admission-refund-clearing",
        "data": [
            ("dock_fees.dat", "admissions.dat"),
            ("reversals.dat", "refunds.dat"),
        ],
        "config": [("harbor_calendar.txt", "gate_calendar.txt")],
    },
]

GO_SPECS = [
    {
        "slug": "go-airport-gate-baggage-hold-release",
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
        "cats_m1": ["MEDICAL", "CUSTOMS"],
        "cats": ["MEDICAL", "CUSTOMS", "MEDICAL"],
        "aliases": [("IN", "MEDICAL"), ("CU", "CUSTOMS"), ("SE", "MEDICAL")],
    },
    {
        "slug": "go-coldchain-pallet-hold-release",
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
        "aliases": [("IN", "FROZEN"), ("CU", "CHILL"), ("SE", "AMBIENT")],
    },
    {
        "slug": "go-datacenter-rack-hold-release",
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
        "aliases": [("IN", "HOT"), ("CU", "WARM"), ("SE", "COLD")],
    },
    {
        "slug": "go-rail-yard-freight-hold-release",
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
        "aliases": [("IN", "HAZ"), ("CU", "DRY"), ("SE", "REF")],
    },
]

RUBY_SPECS = [
    {
        "slug": "ruby-ev-charging-session-release",
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
        "aliases": [("HR", "LEVEL2"), ("QR", "DCFC"), ("CC", "FLEET")],
    },
    {
        "slug": "ruby-hospital-bed-hold-release",
        "source_file": "bed_holds.csv",
        "action_file": "bed_releases.csv",
        "source_id_col": "hold_id",
        "party_col": "patient_id",
        "scope_col": "ward_id",
        "loc_col": "room",
        "category_col": "care_room",
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
        "aliases": [("HR", "ACUTE"), ("QR", "OBS"), ("CC", "ICU")],
    },
    {
        "slug": "ruby-laundry-locker-hold-release",
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
        "aliases": [("HR", "WASH"), ("QR", "DRY"), ("CC", "COMBO")],
    },
    {
        "slug": "ruby-marina-berth-hold-release",
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
        "aliases": [("HR", "SLIP"), ("QR", "DRY"), ("CC", "TRANSIT")],
    },
    {
        "slug": "ruby-ski-resort-lift-gate-release",
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
        "aliases": [("HR", "DAY"), ("QR", "SEASON"), ("CC", "VIP")],
    },
    {
        "slug": "ruby-warehouse-dock-hold-release",
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
        "aliases": [("HR", "LTL"), ("QR", "FTL"), ("CC", "PARCEL")],
    },
]


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def strip_run_batch(text: str) -> str:
    lines = []
    skip_block = False
    for line in text.splitlines():
        if re.match(r"^\s*if grep -q 'SRC-USED\(I\) NOT = \"Y\"'", line):
            skip_block = True
            continue
        if skip_block:
            if line.strip() == "fi":
                skip_block = False
            continue
        if line.strip() == "/app/scripts/run_batch.sh":
            continue
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def fix_cobol_task(task: dict) -> None:
    slug = task["slug"]
    base = ROOT / slug
    for sub in ("data", "samples"):
        d = base / "environment" / sub
        for old, new in task["data"]:
            src = d / old
            dst = d / new
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
            elif src.exists() and dst.exists() and old != new:
                dst.write_bytes(src.read_bytes())
        for old, new in task["config"]:
            src = base / "environment" / "config" / old
            dst = base / "environment" / "config" / new
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
            elif src.exists() and dst.exists() and old != new:
                dst.write_bytes(src.read_bytes())
    for path in base.rglob("steps/**/solution/solve*.sh"):
        write_lf(path, strip_run_batch(path.read_text(encoding="utf-8")))
    print(f"fixed COBOL {slug}")


def go_hold_ok(spec: dict, milestone: int) -> str:
    cats = spec["cats_m1"] if milestone == 1 else list(dict.fromkeys(spec["cats"]))
    return "||".join(f's=="{c}"' for c in cats)


def go_reason_ok(spec: dict) -> str:
    return "||".join(f's=="{r}"' for r in spec["reasons"])


def go_canon_fn(spec: dict, milestone: int) -> str:
    if milestone == 1:
        return 'func canon(s string) string{return strings.ToUpper(strings.TrimSpace(s))}'
    groups: dict[str, list[str]] = {}
    for alias, canon in spec["aliases"]:
        bucket = groups.setdefault(canon, [])
        for token in (alias, canon):
            if token not in bucket:
                bucket.append(token)
    parts = []
    for canon, tokens in groups.items():
        quoted = ",".join(f'"{t}"' for t in tokens)
        parts.append(f"case {quoted}: return \"{canon}\"")
    body = "; ".join(parts)
    return f'func canon(s string) string{{switch strings.ToUpper(strings.TrimSpace(s)){{{body}; default: return strings.ToUpper(strings.TrimSpace(s))}}}}'


def go_match_loop(milestone: int, posted: str) -> str:
    if milestone == 3:
        return f"""best:=-1; for i,src:=range sources{{if src.id==act.id&&src.amount==act.amount&&!src.used&&src.party==act.party&&src.scope==act.scope&&src.loc==act.loc&&hold_typeOK(src.hold_type)&&src.status=="{posted}"&&src.hold_type==hold_type&&reasonOK(act.reason)&&timeOK(src,act,windows){{if best<0||src.ts>sources[best].ts||(src.ts==sources[best].ts&&i<best){{best=i}}}}}}"""
    return f"""best:=-1; for i,src:=range sources{{if src.id==act.id&&src.amount==act.amount&&!src.used&&src.party==act.party&&src.scope==act.scope&&src.loc==act.loc&&hold_typeOK(src.hold_type)&&src.status=="{posted}"&&src.hold_type==hold_type&&reasonOK(act.reason)&&timeOK(src,act,windows){{best=i; break}}}}"""


def go_solve_body(spec: dict, milestone: int) -> str:
    hold_ok = go_hold_ok(spec, milestone)
    reason_ok = go_reason_ok(spec)
    canon_fn = go_canon_fn(spec, milestone)
    match_loop = go_match_loop(milestone, spec["posted_status"])
    if milestone == 3:
        time_fn = 'func timeOK(src rec, act actrec, ws []win) bool{return windowOK(src,act,ws)}'
        win_load = 'windows:=[]win{}; for _,m:=range readCUV("/app/config/windows.csv"){windows=append(windows,win{m["' + spec["window_scope_col"] + '"],m["open_ts"],m["close_ts"],m["state"]})}'
    else:
        time_fn = "func timeOK(src rec, act actrec, ws []win) bool{return tsOK(src,act)}"
        win_load = "windows:=[]win{}"
    sf, af = spec["source_file"], spec["action_file"]
    sid, party, scope, loc = spec["source_id_col"], spec["party_col"], spec["scope_col"], spec["loc_col"]
    cat = spec["category_col"]
    sts, ats, aid = spec["source_ts_col"], spec["action_ts_col"], spec["action_id_col"]
    report, summary = spec["report_file"], spec["summary_file"]
    return f"""package main
import("encoding/csv";"fmt";"os";"path/filepath";"strconv";"strings")
type rec struct{{id,party,scope,hold_type,amount,ts,status,loc string; used bool}}
type actrec struct{{aid,id,party,scope,hold_type,amount,ts,reason,loc string}}
type win struct{{scope,open,close,state string}}
func readCUV(p string) []map[string]string{{f,e:=os.Open(p); if e!=nil{{panic(e)}}; defer f.Close(); r:=csv.NewReader(f); rows,e:=r.ReadAll(); if e!=nil{{panic(e)}}; h:=rows[0]; out:=[]map[string]string{{}}; for _,row:=range rows[1:]{{m:=map[string]string{{}}; for i,k:=range h{{if i<len(row){{m[strings.TrimSpace(k)]=strings.TrimSpace(row[i])}}}}; out=append(out,m)}}; return out}}
func digits(s string) bool{{if len(s)!=14{{return false}}; for _,r:=range s{{if r<'0'||r>'9'{{return false}}}}; return true}}
{canon_fn}
func hold_typeOK(s string) bool{{return {hold_ok}}}
func reasonOK(s string) bool{{return {reason_ok}}}
func tsOK(src rec, act actrec) bool{{return digits(src.ts)&&digits(act.ts)&&act.ts>=src.ts}}
func windowOK(src rec, act actrec, ws []win) bool{{if !digits(src.ts)||!digits(act.ts){{return false}}; for _,w:=range ws{{if w.scope==src.scope&&w.state=="OPEN"&&digits(w.open)&&digits(w.close)&&src.ts>=w.open&&src.ts<=w.close&&act.ts>=src.ts&&act.ts<=w.close{{return true}}}}; return false}}
{time_fn}
func main(){{sources:=[]rec{{}}; for _,m:=range readCUV("/app/data/{sf}"){{sources=append(sources,rec{{m["{sid}"],m["{party}"],m["{scope}"],canon(m["{cat}"]),m["amount"],m["{sts}"],m["status"],m["{loc}"],false}})}}; actions:=[]actrec{{}}; for _,m:=range readCUV("/app/data/{af}"){{actions=append(actions,actrec{{m["{aid}"],m["{sid}"],m["{party}"],m["{scope}"],canon(m["{cat}"]),m["amount"],m["{ats}"],m["reason"],m["{loc}"]}})}}; {win_load}; os.MkdirAll("/app/out",0755); f,_:=os.Create("/app/out/{report}"); defer f.Close(); w:=csv.NewWriter(f); defer w.Flush(); w.Write([]string{{"{aid}","{sid}","{party}","{scope}","{cat}","amount","reason","status"}}); mc,uc,ma,ua:=0,0,0,0; for _,act:=range actions{{hold_type:=act.hold_type; {match_loop}; amt,_:=strconv.Atoi(act.amount); if best>=0{{sources[best].used=true; mc++; ma+=amt; w.Write([]string{{act.aid,act.id,act.party,act.scope,sources[best].hold_type,act.amount,act.reason,"MATCHED"}})}}else{{uc++; ua+=amt; w.Write([]string{{act.aid,act.id,act.party,act.scope,"",act.amount,act.reason,"UNMATCHED"}})}}}}; os.WriteFile(filepath.Clean("/app/out/{summary}"),[]byte(fmt.Sprintf("matched_count=%d\\nmatched_amount=%d\\nunmatched_count=%d\\nunmatched_amount=%d\\n",mc,ma,uc,ua)),0644)}}"""


def go_solve_sh(spec: dict, milestone: int) -> str:
    body = go_solve_body(spec, milestone)
    return f"""#!/bin/bash
set -euo pipefail
cat > /app/cmd/reconcile/main.go <<'GO'
{body}
GO
/app/scripts/run_batch.sh
"""


def ruby_canon(spec: dict, milestone: int) -> str:
    if milestone == 1:
        return "  v.to_s.strip.upcase"
    lines = []
    for alias, canon in spec["aliases"]:
        lines.append(f"  return '{canon}' if v == '{alias}' || v == '{canon}'")
    lines.append("  v.to_s.strip.upcase")
    return "\n".join(lines)


def ruby_rate_ok(spec: dict, milestone: int) -> str:
    cats = spec["cats_m1"] if milestone == 1 else list(dict.fromkeys(spec["cats"]))
    inner = ", ".join(f"'{c}'" for c in cats)
    return f"  [{inner}].include?(v)"


def ruby_time_block(milestone: int) -> str:
    if milestone == 3:
        return """def time_ok?(src, act, windows)
  window_ok?(src, act, windows)
end"""
    return """def time_ok?(src, act, windows)
  return false unless digits?(src[:ts]) && digits?(act[:ts])
  act[:ts] >= src[:ts]
end"""


def ruby_candidate_sort(milestone: int) -> str:
    if milestone == 3:
        return "    candidates.sort_by! { |i| [-sources[i][:ts].to_i, sources[i][:row]] }"
    return "    candidates.sort_by! { |i| sources[i][:row] }"


def ruby_solve_rb(spec: dict, milestone: int) -> str:
    reasons = ", ".join(f"'{r}'" for r in spec["reasons"])
    cat = spec["category_col"]
    report_cols = f"{spec['action_id_col']} {spec['source_id_col']} {spec['party_col']} {spec['scope_col']} {cat} amount reason status"
    return f"""require 'csv'
require 'fileutils'

def canon(v)
{ruby_canon(spec, milestone)}
end

def digits?(v)
  v.to_s.match?(/\\A\\d{{14}}\\z/)
end

def rate_type_ok?(v)
{ruby_rate_ok(spec, milestone)}
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

{ruby_time_block(milestone)}

sources = CSV.read('/app/data/{spec["source_file"]}', headers: true).map.with_index do |r, i|
  {{
    id: r['{spec["source_id_col"]}'].strip,
    party: r['{spec["party_col"]}'].strip,
    scope: r['{spec["scope_col"]}'].strip,
    rate_type: canon(r['{cat}']),
    amount: r['amount'].strip,
    ts: r['{spec["source_ts_col"]}'].strip,
    status: r['status'].strip.upcase,
    loc: r['{spec["loc_col"]}'].strip,
    row: i,
    used: false
  }}
end

actions = CSV.read('/app/data/{spec["action_file"]}', headers: true).map do |r|
  {{
    aid: r['{spec["action_id_col"]}'].strip,
    id: r['{spec["source_id_col"]}'].strip,
    party: r['{spec["party_col"]}'].strip,
    scope: r['{spec["scope_col"]}'].strip,
    rate_type: canon(r['{cat}']),
    amount: r['amount'].strip,
    ts: r['{spec["action_ts_col"]}'].strip,
    reason: r['reason'].strip.upcase,
    loc: r['{spec["loc_col"]}'].strip
  }}
end

windows = CSV.read('/app/config/windows.csv', headers: true).map do |r|
  {{
    scope: r['{spec["window_scope_col"]}'].strip,
    open: r['open_ts'].strip,
    close: r['close_ts'].strip,
    state: r['state'].strip.upcase
  }}
end

FileUtils.mkdir_p('/app/out')
mc = uc = ma = ua = 0

CSV.open('/app/out/{spec["report_file"]}', 'w') do |csv|
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
      next unless src[:status] == '{spec["posted_status"]}'
      next unless rate_type_ok?(src[:rate_type])
      next unless src[:rate_type] == act[:rate_type]
      next unless reason_ok?(act[:reason])
      next unless time_ok?(src, act, windows)
      candidates << i
    end
{ruby_candidate_sort(milestone)}
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

File.write('/app/out/{spec["summary_file"]}', <<~SUMMARY)
  matched_count=#{{mc}}
  matched_amount=#{{ma}}
  unmatched_count=#{{uc}}
  unmatched_amount=#{{ua}}
SUMMARY
"""


def ruby_solve_sh(spec: dict, milestone: int) -> str:
    rb = ruby_solve_rb(spec, milestone)
    return f"""#!/bin/bash
set -euo pipefail
cat > /app/app/reconcile.rb <<'RUBY'
{rb}
RUBY
/app/scripts/run_batch.sh
"""


def fix_go_solves(spec: dict) -> None:
    base = ROOT / spec["slug"]
    solves = {n: go_solve_sh(spec, n) for n in (1, 2, 3)}
    for milestone in (1, 2, 3):
        mdir = base / "steps" / f"milestone_{milestone}" / "solution"
        for n in range(1, milestone + 1):
            write_lf(mdir / f"solve{n}.sh", solves[n])
    print(f"fixed Go {spec['slug']}")


def fix_ruby_solves(spec: dict) -> None:
    base = ROOT / spec["slug"]
    solves = {n: ruby_solve_sh(spec, n) for n in (1, 2, 3)}
    for milestone in (1, 2, 3):
        mdir = base / "steps" / f"milestone_{milestone}" / "solution"
        for n in range(1, milestone + 1):
            write_lf(mdir / f"solve{n}.sh", strip_run_batch(solves[n]))
    starter = base / "environment" / "app" / "reconcile.rb"
    if starter.exists():
        text = starter.read_text(encoding="utf-8")
        if spec["slug"] == "ruby-hospital-bed-hold-release":
            text = text.replace("care_level", "care_room")
        write_lf(starter, text)
    data_dir = base / "environment" / "data"
    src = spec["source_file"]
    act = spec["action_file"]
    for name in ("sessions.csv", "adjustments.csv"):
        p = data_dir / name
        if p.exists():
            target = data_dir / (src if name == "sessions.csv" else act)
            if not target.exists():
                shutil.copy2(p, target)
    print(f"fixed Ruby {spec['slug']}")


def main() -> None:
    for task in COBOL_TASKS:
        fix_cobol_task(task)
    for spec in GO_SPECS:
        fix_go_solves(spec)
    for spec in RUBY_SPECS:
        fix_ruby_solves(spec)


if __name__ == "__main__":
    main()
