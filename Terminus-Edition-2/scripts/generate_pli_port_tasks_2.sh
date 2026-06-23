#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source_helpers() {
  write_common_dockerfile() {
    local task_dir="$1"
    cat > "$task_dir/environment/Dockerfile" <<'EOF'
FROM python:3.11-slim-bookworm@sha256:cd67330292a51e2963156f74ff340455d66b2172e9190e99f40dff9357471177
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gawk tmux asciinema && rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5
COPY src/ /app/src/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/
RUN mkdir -p /app/out /app/build && chmod +x /app/scripts/*.sh
EOF
  }
  write_task_toml() {
    local task_dir="$1" tags="$2"
    cat > "$task_dir/task.toml" <<EOF
version = "2.0"
[metadata]
author_name = "anonymous"
author_email = "anonymous@example.com"
difficulty = "hard"
category = "debugging"
subcategories = []
number_of_milestones = 3
codebase_size = "small"
languages = ["pli", "bash"]
tags = [$tags]
expert_time_estimate_min = 100
junior_time_estimate_min = 260
[agent]
timeout_sec = 1800
[verifier]
timeout_sec = 900
[environment]
allow_internet = false
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"
[[steps]]
name = "milestone_1"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
[[steps]]
name = "milestone_2"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
[[steps]]
name = "milestone_3"
[steps.agent]
timeout_sec = 1800.0
[steps.verifier]
timeout_sec = 900.0
EOF
  }
  write_test_sh() {
    local milestone="$1" test_py="$2" dir="$3"
    cat > "$dir/steps/milestone_${milestone}/tests/test.sh" <<EOF
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/${test_py} -rA
if [ \$? -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
EOF
    chmod +x "$dir/steps/milestone_${milestone}/tests/test.sh"
  }
  write_solve_chain() {
    local task_dir="$1" milestone="$2" body="$3"
    local sol_dir="$task_dir/steps/milestone_${milestone}/solution"
    cat > "$sol_dir/solve${milestone}.sh" <<EOF
#!/bin/bash
set -euo pipefail
$body
/app/scripts/run_batch.sh
EOF
    chmod +x "$sol_dir/solve${milestone}.sh"
    if [[ "$milestone" == "1" ]]; then
      printf '%s\n' '#!/bin/bash' 'set -euo pipefail' 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' 'bash "$SCRIPT_DIR/solve1.sh"' > "$sol_dir/solve.sh"
    else
      printf '%s\n' '#!/bin/bash' 'set -euo pipefail' "SCRIPT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"" "bash \"\$SCRIPT_DIR/solve${milestone}.sh\"" > "$sol_dir/solve.sh"
    fi
    chmod +x "$sol_dir/solve.sh"
  }
}
source_helpers

# Shared reconciler awk template for wire + fragment + ledger tasks
write_reconciler_awk() {
  local path="$1"
  local src_file="$2"
  local batch_file="$3"
  local left_psv="$4"
  local right_psv="$5"
  local win_psv="$6"
  local out_report="$7"
  local out_summary="$8"
  local key_fields="$9"
  local left_ts="${10}"
  local right_ts="${11}"
  local eligible_key="${12}"
  local open_key="${13}"
  local reason_prefix="${14}"
  local emit_field="${15}"
  local accept_status="${16}"
  local reject_status="${17}"
  local matched_count_key="${18}"
  local matched_amt_key="${19}"
  local rejected_count_key="${20}"
  local rejected_amt_key="${21}"
  local amt_field="${22}"

  cat > "$path" <<AWKEOF
BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("$key_fields", key_fields, " "); nkeys = length(key_fields)
    SRC_FILE = "$left_psv"; ACT_FILE = "$right_psv"; WIN_FILE = "$win_psv"
    RULES_FILE = (APP "/src/$src_file"); BATCH_FILE = (APP "/src/$batch_file")
    REPORT = (APP "/out/$out_report"); SUMMARY = (APP "/out/$out_summary")
    LEFT_TS = "$left_ts"; RIGHT_TS = "$right_ts"
    ELIGIBLE_KEY = "$eligible_key"; OPEN_KEY = "$open_key"; REASON_PREFIX = "$reason_prefix"
    EMIT_FIELD = "$emit_field"; ACCEPT = "$accept_status"; REJECT = "$reject_status"
    MC_KEY = "$matched_count_key"; MA_KEY = "$matched_amt_key"
    RC_KEY = "$rejected_count_key"; RA_KEY = "$rejected_amt_key"; AMT_FIELD = "$amt_field"
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < RULES_FILE) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(RULES_FILE)
}
function load_batch(    line, parts) {
    while ((getline line < BATCH_FILE) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
    }
    close(BATCH_FILE)
}
function canon(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k) }
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+\$/ }
function keys_ok(si, ai,    fi, f, pk) {
    if (KEY_COMPARE == "PREFIX5") {
        pk = key_fields[1]
        return substr(src[si, pk], 1, 5) == substr(act[ai, pk], 1, 5) && src[si, AMT_FIELD] == act[ai, AMT_FIELD]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(src[si, f]) != canon(act[ai, f])) return 0
    }
    return 1
}
function reason_ok(code,    vi, key) {
    for (vi = 1; vi <= 3; vi++) {
        key = REASON_PREFIX vi
        if (up(code) == up(rules[key])) return 1
    }
    return 0
}
function win_ok(si, ai,    wi, o, c, st, at, craft) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, LEFT_TS]; at = act[ai, RIGHT_TS]
    if (!nts(st) || !nts(at)) return 0
    craft = src[si, key_fields[2]]
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, key_fields[2]] != craft) continue
        if (up(win[wi, "state"]) != up(rules[OPEN_KEY])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function read_psv(path, arr, count, hdr,    line, i) {
    count = 0
    while ((getline line < path) > 0) {
        if (count == 0) { split(line, hdr, "|"); count = -1; continue }
        count++
        split(line, fields, "|")
        for (i = 1; i <= length(hdr); i++) arr[count, hdr[i]] = trim(fields[i])
    }
    close(path)
    return count
}
END {
    load_rules(); load_batch(); eligible = up(rules[ELIGIBLE_KEY])
    scount = read_psv(APP "/" SRC_FILE, src, scount, chdr)
    acount = read_psv(APP "/" ACT_FILE, act, acount, ahdr)
    if (WINDOW_MODE == "ON") wcount = read_psv(APP "/" WIN_FILE, win, wcount, whdr)
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    hdr_out = ahdr[1]
    for (hi = 2; hi <= 4; hi++) hdr_out = hdr_out "|" ahdr[hi]
    hdr_out = hdr_out "|" EMIT_FIELD "|" AMT_FIELD "|" ahdr[7] "|status"
    print hdr_out > REPORT
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!reason_ok(act[ai, ahdr[7]])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || src[si, LEFT_TS] > src[best, LEFT_TS] || (src[si, LEFT_TS] == src[best, LEFT_TS] && si < best)) best = si
        }
        amt = 0 + act[ai, AMT_FIELD]
        if (best == 0) { uc++; ua += amt; emit = ""; status = REJECT }
        else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; emit = canon(src[best, EMIT_FIELD]); status = ACCEPT
        }
        row = act[ai, ahdr[1]]
        for (hi = 2; hi <= 4; hi++) row = row "|" act[ai, ahdr[hi]]
        row = row "|" emit "|" act[ai, AMT_FIELD] "|" act[ai, ahdr[7]] "|" status
        print row >> REPORT
    }
    print MC_KEY "=" mc > SUMMARY
    print MA_KEY "=" ma >> SUMMARY
    print RC_KEY "=" uc >> SUMMARY
    print RA_KEY "=" ua >> SUMMARY
}
AWKEOF
}

# ---- Task 2: treasury wire batch ----
T2="pli-treasury-wire-batch-adjudicator"
rm -rf "$T2"
mkdir -p "$T2/environment"/{scripts,src,data,config,docs,samples}
mkdir -p "$T2/steps"/{milestone_1,milestone_2,milestone_3}/{tests,solution}
write_task_toml "$T2" '"pli", "batch", "treasury", "wire"'
write_common_dockerfile "$T2"
echo 'out/' > "$T2/environment/.dockerignore"
cat > "$T2/environment/scripts/run_batch.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
gawk -f /app/scripts/pli_wire.awk
EOF
chmod +x "$T2/environment/scripts/run_batch.sh"

write_reconciler_awk "$T2/environment/scripts/pli_wire.awk" \
  "wire_rules.pli" "wire_batch.pli" "data/clearing.psv" "data/claims.psv" "config/clearing_windows.psv" \
  "wire_report.csv" "wire_summary.txt" \
  "wire_id account amount_cents rail_code branch_id" \
  "posted_ts" "claim_ts" "ELIGIBLE_STATE" "OPEN_CLEAR_STATE" "REASON_" \
  "rail_code" "CLEARED" "RETURNED" \
  "cleared_count" "cleared_amount_cents" "returned_count" "returned_amount_cents" "amount_cents"

cat > "$T2/environment/src/wire_rules.pli" <<'EOF'
DCL ELIGIBLE_STATE CHAR(12) INIT('POSTED');
DCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');
DCL REASON_1 CHAR(12) INIT('SETTLE');
DCL REASON_2 CHAR(12) INIT('RECALL');
DCL REASON_3 CHAR(12) INIT('ADJUST');
DCL ALIAS_1 CHAR(20) INIT('F=>FED');
DCL ALIAS_2 CHAR(20) INIT('A=>ACH');
DCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');
EOF
cat > "$T2/environment/src/wire_batch.pli" <<'EOF'
/* PL/I wire batch adjudicator control deck. */
%SET KEY_COMPARE PREFIX5
%SET CONSUME OFF
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF
cat > "$T2/environment/data/clearing.psv" <<'EOF'
wire_id|account|amount_cents|rail_code|posted_ts|state|branch_id
W-10001|991100|50000|FED|20260612120000|POSTED|NYC
EOF
cat > "$T2/environment/data/claims.psv" <<'EOF'
claim_id|wire_id|account|amount_cents|rail_code|claim_ts|reason_code|branch_id
CLM-1|W-10001|991100|50000|FED|20260612120500|SETTLE|NYC
EOF
cat > "$T2/environment/config/clearing_windows.psv" <<'EOF'
account|open_ts|close_ts|state
991100|20260612115900|20260612123000|OPEN
EOF

# Fix window key for wire task - account not craft_id. Patch awk for wire separately.
cat > "$T2/environment/scripts/pli_wire.awk" <<'AWKEOF'
BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("wire_id account amount_cents rail_code branch_id", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/wire_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/wire_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/wire_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
    }
    close(APP "/src/wire_batch.pli")
}
function canon(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k) }
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "wire_id"], 1, 5) == substr(act[ai, "wire_id"], 1, 5) && src[si, "amount_cents"] == act[ai, "amount_cents"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(src[si, f]) != canon(act[ai, f])) return 0
    }
    return 1
}
function reason_ok(code,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(code) == up(rules["REASON_" vi])) return 1
    return 0
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "posted_ts"]; at = act[ai, "claim_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "account"] != src[si, "account"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_CLEAR_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    scount = acount = wcount = 0
    while ((getline line < (APP "/data/clearing.psv")) > 0) {
        if (scount == 0) { split(line, chdr, "|"); continue }
        scount++; split(line, cf, "|"); for (i = 1; i <= length(chdr); i++) src[scount, chdr[i]] = trim(cf[i])
    }
    close(APP "/data/clearing.psv")
    while ((getline line < (APP "/data/claims.psv")) > 0) {
        if (acount == 0) { split(line, ahdr, "|"); continue }
        acount++; split(line, af, "|"); for (i = 1; i <= length(ahdr); i++) act[acount, ahdr[i]] = trim(af[i])
    }
    close(APP "/data/claims.psv")
    if (WINDOW_MODE == "ON") {
        while ((getline line < (APP "/config/clearing_windows.psv")) > 0) {
            if (wcount == 0) { split(line, whdr, "|"); continue }
            wcount++; split(line, wf, "|"); for (i = 1; i <= length(whdr); i++) win[wcount, whdr[i]] = trim(wf[i])
        }
        close(APP "/config/clearing_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "claim_id|wire_id|account|branch_id|rail_code|amount_cents|reason_code|status" > (APP "/out/wire_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!reason_ok(act[ai, "reason_code"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || src[si, "posted_ts"] > src[best, "posted_ts"] || (src[si, "posted_ts"] == src[best, "posted_ts"] && si < best)) best = si
        }
        amt = 0 + act[ai, "amount_cents"]
        if (best == 0) { uc++; ua += amt; rail = ""; status = "RETURNED" }
        else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; rail = canon(src[best, "rail_code"]); status = "CLEARED"
        }
        print act[ai, "claim_id"], act[ai, "wire_id"], act[ai, "account"], act[ai, "branch_id"], rail, act[ai, "amount_cents"], act[ai, "reason_code"], status >> (APP "/out/wire_report.csv")
    }
    print "cleared_count=" mc > (APP "/out/wire_summary.txt")
    print "cleared_amount_cents=" ma >> (APP "/out/wire_summary.txt")
    print "returned_count=" uc >> (APP "/out/wire_summary.txt")
    print "returned_amount_cents=" ua >> (APP "/out/wire_summary.txt")
}
AWKEOF

cat > "$T2/environment/docs/operations.md" <<'EOF'
# Treasury Wire Batch Adjudicator
Reconciles `/app/data/claims.psv` against `/app/data/clearing.psv` using PL/I decks in `/app/src/`.
EOF
echo "wire_id|account" > "$T2/environment/samples/example.psv"

cat > "$T2/steps/milestone_1/instruction.md" <<'EOF'
The treasury wire PL/I adjudicator clears too few claims. Fix `/app/src/wire_batch.pli`, `/app/src/wire_rules.pli`, or the batch harness so `/app/data/claims.psv` adjudicates against `/app/data/clearing.psv`.

Milestone 1 requires full agreement on `wire_id`, `account`, `amount_cents`, `rail_code`, and `branch_id`, clearing `state` equal to `ELIGIBLE_STATE`, and `reason_code` one of `REASON_1`, `REASON_2`, or `REASON_3`. Each clearing row may be consumed once. Preserve claim order. Write `/app/out/wire_report.csv` and `/app/out/wire_summary.txt`.

Status must be exactly `CLEARED` or `RETURNED`.
EOF
cat > "$T2/steps/milestone_2/instruction.md" <<'EOF'
The treasury wire PL/I adjudicator clears too few claims. Fix `/app/src/wire_batch.pli`, `/app/src/wire_rules.pli`, or the batch harness.

Milestone 2 keeps milestone 1 rules and enables `ALIAS_*` rail normalization (`raw=>canonical`, case-insensitive). Emit canonical `rail_code` for cleared rows.
EOF
cat > "$T2/steps/milestone_3/instruction.md" <<'EOF'
The treasury wire PL/I adjudicator clears too few claims. Fix `/app/src/wire_batch.pli`, `/app/src/wire_rules.pli`, or the batch harness.

Milestone 3 keeps prior rules and adds `/app/config/clearing_windows.psv`. Posted and claim timestamps must fall inside an open clearing window per account using `OPEN_CLEAR_STATE`. Tie-break on latest `posted_ts` then earliest clearing row.
EOF

# Wire tests (abbreviated but complete)
for m in 1 2 3; do
  cp "$ROOT/pli-orbit-downlink-frame-auditor/steps/milestone_${m}/tests/test_m${m}.py" "$T2/steps/milestone_${m}/tests/test_m${m}.py" 2>/dev/null || true
done

cat > "$T2/steps/milestone_1/tests/test_m1.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP = Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def rules(st="POSTED",rs=("SETTLE","RECALL","ADJUST")):
    (APP/"src/wire_rules.pli").write_text("\n".join([
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{st}');","DCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');",
        f"DCL REASON_1 CHAR(12) INIT('{rs[0]}');",f"DCL REASON_2 CHAR(12) INIT('{rs[1]}');",f"DCL REASON_3 CHAR(12) INIT('{rs[2]}');",
        "DCL ALIAS_1 CHAR(20) INIT('F=>FED');","DCL ALIAS_2 CHAR(20) INIT('A=>ACH');","DCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');"])+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    rows=list(csv.DictReader((APP/"out/wire_report.csv").open()))
    summary={k:int(v) for k,v in (l.split("=",1) for l in (APP/"out/wire_summary.txt").read_text().splitlines())}
    return rows, summary
def test_m1():
    rules(st="LIVE",rs=("OK","WATCH","DONE"))
    w(APP/"data/clearing.psv",["wire_id","account","amount_cents","rail_code","posted_ts","state","branch_id"],[
        ["W-1","991100","10","FED","20260612120000","LIVE","NYC"],
        ["W-2","991200","20","ACH","20260612120100","BAD","NYC"],
        ["W-3","991300","30","SWIFT","20260612120200","LIVE","BOS"],
    ])
    w(APP/"data/claims.psv",["claim_id","wire_id","account","amount_cents","rail_code","claim_ts","reason_code","branch_id"],[
        ["C1","W-1","991100","10","FED","20260612120500","OK","NYC"],
        ["C2","W-1","991100","10","FED","20260612120600","OK","NYC"],
        ["C3","W-2","991200","20","ACH","20260612120700","OK","NYC"],
        ["C4","W-3","991300","30","SWIFT","20260612120700","WATCH","BOS"],
        ["C5","W-3","991300","31","SWIFT","20260612120700","WATCH","BOS"],
        ["C6","W-3","991300","30","SWIFT","20260612120700","NOPE","BOS"],
    ])
    w(APP/"config/clearing_windows.psv",["account","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows,summary=run()
    assert [r["status"] for r in rows]==["CLEARED","RETURNED","RETURNED","CLEARED","RETURNED","RETURNED"]
    assert rows[1]["rail_code"]==""
    assert summary=={"cleared_count":2,"cleared_amount_cents":40,"returned_count":4,"returned_amount_cents":81}
PYEOF

cat > "$T2/steps/milestone_2/tests/test_m2.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/wire_report.csv").open()))
def test_m2():
    (APP/"src/wire_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\nDCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');\nDCL REASON_1 CHAR(12) INIT('GO');\nDCL REASON_2 CHAR(12) INIT('CHK');\nDCL REASON_3 CHAR(12) INIT('WAIT');\nDCL ALIAS_1 CHAR(20) INIT('f=>FED');\nDCL ALIAS_2 CHAR(20) INIT('a=>ACH');\nDCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');\n")
    w(APP/"data/clearing.psv",["wire_id","account","amount_cents","rail_code","posted_ts","state","branch_id"],[["W-9","991100","99","f","20260612120000","LIVE","NYC"]])
    w(APP/"data/claims.psv",["claim_id","wire_id","account","amount_cents","rail_code","claim_ts","reason_code","branch_id"],[["C9","W-9","991100","99","FED","20260612120500","go","NYC"]])
    w(APP/"config/clearing_windows.psv",["account","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="CLEARED" and rows[0]["rail_code"]=="FED"
PYEOF

cat > "$T2/steps/milestone_3/tests/test_m3.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/wire_report.csv").open()))
def test_m3():
    (APP/"src/wire_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\nDCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');\nDCL REASON_1 CHAR(12) INIT('OK');\nDCL REASON_2 CHAR(12) INIT('WATCH');\nDCL REASON_3 CHAR(12) INIT('DONE');\nDCL ALIAS_1 CHAR(20) INIT('F=>FED');\nDCL ALIAS_2 CHAR(20) INIT('A=>ACH');\nDCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');\n")
    w(APP/"data/clearing.psv",["wire_id","account","amount_cents","rail_code","posted_ts","state","branch_id"],[
        ["W-A","991100","10","FED","20260612120000","OPEN","NYC"],
        ["W-A","991100","10","FED","20260612120100","OPEN","NYC"],
    ])
    w(APP/"data/claims.psv",["claim_id","wire_id","account","amount_cents","rail_code","claim_ts","reason_code","branch_id"],[["C-W","W-A","991100","10","FED","20260612120500","OK","NYC"]])
    w(APP/"config/clearing_windows.psv",["account","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    assert run()[0]["status"]=="CLEARED"
    w(APP/"data/claims.psv",["claim_id","wire_id","account","amount_cents","rail_code","claim_ts","reason_code","branch_id"],[["C-X","W-A","991100","10","FED","20260612130000","OK","NYC"]])
    assert run()[0]["status"]=="RETURNED"
PYEOF

for m in 1 2 3; do write_test_sh "$m" "test_m${m}.py" "$T2"; done

B='/* PL/I wire batch adjudicator control deck. */'
write_solve_chain "$T2" 1 "cat > /app/src/wire_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF"
write_solve_chain "$T2" 2 "cat > /app/src/wire_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
EOF"
write_solve_chain "$T2" 3 "cat > /app/src/wire_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
EOF"
echo "Created $T2"

# ---- Task 3: distributed fragment ledger ----
T3="pli-distributed-fragment-ledger-reconciler"
rm -rf "$T3"
mkdir -p "$T3/environment"/{scripts,src,data,config,docs,samples}
mkdir -p "$T3/steps"/{milestone_1,milestone_2,milestone_3}/{tests,solution}
write_task_toml "$T3" '"pli", "batch", "ledger", "fragments"'
write_common_dockerfile "$T3"
echo 'out/' > "$T3/environment/.dockerignore"
cat > "$T3/environment/scripts/run_batch.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
gawk -f /app/scripts/pli_fragment.awk
EOF
chmod +x "$T3/environment/scripts/run_batch.sh"

cat > "$T3/environment/scripts/pli_fragment.awk" <<'AWKEOF'
BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    DUP_MODE = "SKIP"; APP = "/app"; FS = OFS = "|"
    split("fragment_id parent_id shard_value channel ingest_class", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/fragment_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/fragment_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/fragment_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
        else if (parts[2] == "DUP_MODE") DUP_MODE = parts[3]
    }
    close(APP "/src/fragment_batch.pli")
}
function canon(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k) }
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "fragment_id"], 1, 5) == substr(act[ai, "fragment_id"], 1, 5) && src[si, "shard_value"] == act[ai, "shard_value"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(src[si, f]) != canon(act[ai, f])) return 0
    }
    return 1
}
function opcode_ok(code,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(code) == up(rules["OPCODE_" vi])) return 1
    return 0
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "ingest_ts"]; at = act[ai, "merge_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "channel"] != src[si, "channel"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_SHARD_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    scount = acount = wcount = 0
    while ((getline line < (APP "/data/fragments.psv")) > 0) {
        if (scount == 0) { split(line, chdr, "|"); continue }
        scount++; split(line, cf, "|"); for (i = 1; i <= length(chdr); i++) src[scount, chdr[i]] = trim(cf[i])
    }
    close(APP "/data/fragments.psv")
    while ((getline line < (APP "/data/merges.psv")) > 0) {
        if (acount == 0) { split(line, ahdr, "|"); continue }
        acount++; split(line, af, "|"); for (i = 1; i <= length(ahdr); i++) act[acount, ahdr[i]] = trim(af[i])
    }
    close(APP "/data/merges.psv")
    if (WINDOW_MODE == "ON") {
        while ((getline line < (APP "/config/shard_windows.psv")) > 0) {
            if (wcount == 0) { split(line, whdr, "|"); continue }
            wcount++; split(line, wf, "|"); for (i = 1; i <= length(whdr); i++) win[wcount, whdr[i]] = trim(wf[i])
        }
        close(APP "/config/shard_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "merge_id|fragment_id|parent_id|channel|ingest_class|shard_value|opcode|status" > (APP "/out/fragment_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!opcode_ok(act[ai, "opcode"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || src[si, "ingest_ts"] > src[best, "ingest_ts"] || (src[si, "ingest_ts"] == src[best, "ingest_ts"] && si < best)) best = si
        }
        amt = 0 + act[ai, "shard_value"]
        if (best == 0) { uc++; ua += amt; cls = ""; status = "ORPHAN" }
        else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; cls = canon(src[best, "ingest_class"]); status = "LINKED"
        }
        print act[ai, "merge_id"], act[ai, "fragment_id"], act[ai, "parent_id"], act[ai, "channel"], cls, act[ai, "shard_value"], act[ai, "opcode"], status >> (APP "/out/fragment_report.csv")
    }
    print "linked_count=" mc > (APP "/out/fragment_summary.txt")
    print "linked_shards=" ma >> (APP "/out/fragment_summary.txt")
    print "orphan_count=" uc >> (APP "/out/fragment_summary.txt")
    print "orphan_shards=" ua >> (APP "/out/fragment_summary.txt")
}
AWKEOF

cat > "$T3/environment/src/fragment_rules.pli" <<'EOF'
DCL ELIGIBLE_STATE CHAR(12) INIT('ACTIVE');
DCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');
DCL OPCODE_1 CHAR(12) INIT('APPEND');
DCL OPCODE_2 CHAR(12) INIT('RELINK');
DCL OPCODE_3 CHAR(12) INIT('CLOSE');
DCL ALIAS_1 CHAR(20) INIT('N=>NORTH');
DCL ALIAS_2 CHAR(20) INIT('S=>SOUTH');
DCL ALIAS_3 CHAR(20) INIT('E=>EDGE');
EOF
cat > "$T3/environment/src/fragment_batch.pli" <<'EOF'
/* PL/I fragment ledger reconciler control deck. */
%SET KEY_COMPARE PREFIX5
%SET CONSUME OFF
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
%SET DUP_MODE SKIP
EOF
cat > "$T3/environment/data/fragments.psv" <<'EOF'
fragment_id|parent_id|shard_value|channel|ingest_ts|state|ingest_class
FRG-10001|ROOT-1|42|NORTH|20260612120000|ACTIVE|LEDGER
EOF
cat > "$T3/environment/data/merges.psv" <<'EOF'
merge_id|fragment_id|parent_id|shard_value|channel|merge_ts|opcode|ingest_class
MRG-1|FRG-10001|ROOT-1|42|NORTH|20260612120500|APPEND|LEDGER
EOF
cat > "$T3/environment/config/shard_windows.psv" <<'EOF'
channel|open_ts|close_ts|state
NORTH|20260612115900|20260612123000|OPEN
EOF
cat > "$T3/environment/docs/operations.md" <<'EOF'
# Distributed Fragment Ledger Reconciler
Links `/app/data/merges.psv` to `/app/data/fragments.psv` via PL/I control decks.
EOF
echo "fragment_id|parent_id" > "$T3/environment/samples/example.psv"

cat > "$T3/steps/milestone_1/instruction.md" <<'EOF'
The distributed fragment PL/I reconciler orphans valid merges. Fix `/app/src/fragment_batch.pli`, `/app/src/fragment_rules.pli`, or the batch harness so `/app/data/merges.psv` links against `/app/data/fragments.psv`.

Milestone 1 requires full agreement on `fragment_id`, `parent_id`, `shard_value`, `channel`, and `ingest_class`, fragment `state` equal to `ELIGIBLE_STATE`, and `opcode` one of `OPCODE_1`, `OPCODE_2`, or `OPCODE_3`. Each fragment row may be consumed once. Preserve merge order. Write `/app/out/fragment_report.csv` and `/app/out/fragment_summary.txt`.

Status must be exactly `LINKED` or `ORPHAN`.
EOF
cat > "$T3/steps/milestone_2/instruction.md" <<'EOF'
The distributed fragment PL/I reconciler orphans valid merges. Fix `/app/src/fragment_batch.pli`, `/app/src/fragment_rules.pli`, or the batch harness.

Milestone 2 keeps milestone 1 rules and enables `ALIAS_*` channel normalization. Emit canonical `ingest_class` for linked rows.
EOF
cat > "$T3/steps/milestone_3/instruction.md" <<'EOF'
The distributed fragment PL/I reconciler orphans valid merges. Fix `/app/src/fragment_batch.pli`, `/app/src/fragment_rules.pli`, or the batch harness.

Milestone 3 keeps prior rules and adds `/app/config/shard_windows.psv`. Ingest and merge timestamps must fall inside an open shard window per channel using `OPEN_SHARD_STATE`. Tie-break on latest `ingest_ts` then earliest fragment row.
EOF

cat > "$T3/steps/milestone_1/tests/test_m1.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def rules(st="ACTIVE",ops=("APPEND","RELINK","CLOSE")):
    (APP/"src/fragment_rules.pli").write_text("\n".join([
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{st}');","DCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');",
        f"DCL OPCODE_1 CHAR(12) INIT('{ops[0]}');",f"DCL OPCODE_2 CHAR(12) INIT('{ops[1]}');",f"DCL OPCODE_3 CHAR(12) INIT('{ops[2]}');",
        "DCL ALIAS_1 CHAR(20) INIT('N=>NORTH');","DCL ALIAS_2 CHAR(20) INIT('S=>SOUTH');","DCL ALIAS_3 CHAR(20) INIT('E=>EDGE');"])+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    rows=list(csv.DictReader((APP/"out/fragment_report.csv").open()))
    summary={k:int(v) for k,v in (l.split("=",1) for l in (APP/"out/fragment_summary.txt").read_text().splitlines())}
    return rows,summary
def test_m1():
    rules(st="LIVE",ops=("OK","WATCH","DONE"))
    w(APP/"data/fragments.psv",["fragment_id","parent_id","shard_value","channel","ingest_ts","state","ingest_class"],[
        ["FRG-1","P-1","10","NORTH","20260612120000","LIVE","LEDGER"],
        ["FRG-2","P-2","20","SOUTH","20260612120100","BAD","LEDGER"],
        ["FRG-3","P-3","30","EDGE","20260612120200","LIVE","LEDGER"],
    ])
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[
        ["M1","FRG-1","P-1","10","NORTH","20260612120500","OK","LEDGER"],
        ["M2","FRG-1","P-1","10","NORTH","20260612120600","OK","LEDGER"],
        ["M3","FRG-2","P-2","20","SOUTH","20260612120700","OK","LEDGER"],
        ["M4","FRG-3","BAD","30","EDGE","20260612120700","WATCH","LEDGER"],
        ["M5","FRG-3","P-3","31","EDGE","20260612120700","WATCH","LEDGER"],
        ["M6","FRG-3","P-3","30","EDGE","20260612120700","NOPE","LEDGER"],
    ])
    w(APP/"config/shard_windows.psv",["channel","open_ts","close_ts","state"],[["NORTH","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows,summary=run()
    assert [r["status"] for r in rows]==["LINKED","ORPHAN","ORPHAN","ORPHAN","ORPHAN","ORPHAN"]
    assert rows[1]["ingest_class"]==""
    assert summary=={"linked_count":1,"linked_shards":10,"orphan_count":5,"orphan_shards":121}
PYEOF

cat > "$T3/steps/milestone_2/tests/test_m2.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/fragment_report.csv").open()))
def test_m2():
    (APP/"src/fragment_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\nDCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');\nDCL OPCODE_1 CHAR(12) INIT('GO');\nDCL OPCODE_2 CHAR(12) INIT('CHK');\nDCL OPCODE_3 CHAR(12) INIT('WAIT');\nDCL ALIAS_1 CHAR(20) INIT('n=>NORTH');\nDCL ALIAS_2 CHAR(20) INIT('lg=>LEDGER');\nDCL ALIAS_3 CHAR(20) INIT('e=>EDGE');\n")
    w(APP/"data/fragments.psv",["fragment_id","parent_id","shard_value","channel","ingest_ts","state","ingest_class"],[["FRG-9","P-9","7","n","20260612120000","LIVE","lg"]])
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[["M9","FRG-9","P-9","7","NORTH","20260612120500","go","LEDGER"]])
    w(APP/"config/shard_windows.psv",["channel","open_ts","close_ts","state"],[["NORTH","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="LINKED" and rows[0]["ingest_class"]=="LEDGER"
PYEOF

cat > "$T3/steps/milestone_3/tests/test_m3.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/fragment_report.csv").open()))
def test_m3():
    (APP/"src/fragment_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\nDCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');\nDCL OPCODE_1 CHAR(12) INIT('OK');\nDCL OPCODE_2 CHAR(12) INIT('WATCH');\nDCL OPCODE_3 CHAR(12) INIT('DONE');\nDCL ALIAS_1 CHAR(20) INIT('N=>NORTH');\nDCL ALIAS_2 CHAR(20) INIT('S=>SOUTH');\nDCL ALIAS_3 CHAR(20) INIT('E=>EDGE');\n")
    w(APP/"data/fragments.psv",["fragment_id","parent_id","shard_value","channel","ingest_ts","state","ingest_class"],[
        ["FRG-A","P-A","5","NORTH","20260612120000","OPEN","LEDGER"],
        ["FRG-A","P-A","5","NORTH","20260612120100","OPEN","LEDGER"],
    ])
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[["M-W","FRG-A","P-A","5","NORTH","20260612120500","OK","LEDGER"]])
    w(APP/"config/shard_windows.psv",["channel","open_ts","close_ts","state"],[["NORTH","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    assert run()[0]["status"]=="LINKED"
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[["M-X","FRG-A","P-A","5","NORTH","20260612130000","OK","LEDGER"]])
    assert run()[0]["status"]=="ORPHAN"
PYEOF

for m in 1 2 3; do write_test_sh "$m" "test_m${m}.py" "$T3"; done
B='/* PL/I fragment ledger reconciler control deck. */'
write_solve_chain "$T3" 1 "cat > /app/src/fragment_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
%SET DUP_MODE SKIP
EOF"
write_solve_chain "$T3" 2 "cat > /app/src/fragment_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
%SET DUP_MODE SKIP
EOF"
write_solve_chain "$T3" 3 "cat > /app/src/fragment_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
%SET DUP_MODE SKIP
EOF"
echo "Created $T3"

# ---- Task 4: general ledger posting normalizer ----
T4="pli-general-ledger-posting-normalizer"
rm -rf "$T4"
mkdir -p "$T4/environment"/{scripts,src,data,config,docs,samples}
mkdir -p "$T4/steps"/{milestone_1,milestone_2,milestone_3}/{tests,solution}
write_task_toml "$T4" '"pli", "batch", "ledger", "posting"'
write_common_dockerfile "$T4"
echo 'out/' > "$T4/environment/.dockerignore"
cat > "$T4/environment/scripts/run_batch.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
gawk -f /app/scripts/pli_posting.awk
EOF
chmod +x "$T4/environment/scripts/run_batch.sh"

cat > "$T4/environment/scripts/pli_posting.awk" <<'AWKEOF'
BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("posting_id account amount_cents ctrl_hash ledger_class", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/posting_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/posting_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/posting_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
    }
    close(APP "/src/posting_batch.pli")
}
function canon(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k) }
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "posting_id"], 1, 5) == substr(act[ai, "posting_id"], 1, 5) && src[si, "amount_cents"] == act[ai, "amount_cents"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(src[si, f]) != canon(act[ai, f])) return 0
    }
    return 1
}
function entry_ok(code,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(code) == up(rules["ENTRY_" vi])) return 1
    return 0
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "book_ts"]; at = act[ai, "post_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "account"] != src[si, "account"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_BOOK_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    scount = acount = wcount = 0
    while ((getline line < (APP "/data/journal.psv")) > 0) {
        if (scount == 0) { split(line, chdr, "|"); continue }
        scount++; split(line, cf, "|"); for (i = 1; i <= length(chdr); i++) src[scount, chdr[i]] = trim(cf[i])
    }
    close(APP "/data/journal.psv")
    while ((getline line < (APP "/data/postings.psv")) > 0) {
        if (acount == 0) { split(line, ahdr, "|"); continue }
        acount++; split(line, af, "|"); for (i = 1; i <= length(ahdr); i++) act[acount, ahdr[i]] = trim(af[i])
    }
    close(APP "/data/postings.psv")
    if (WINDOW_MODE == "ON") {
        while ((getline line < (APP "/config/book_windows.psv")) > 0) {
            if (wcount == 0) { split(line, whdr, "|"); continue }
            wcount++; split(line, wf, "|"); for (i = 1; i <= length(whdr); i++) win[wcount, whdr[i]] = trim(wf[i])
        }
        close(APP "/config/book_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "entry_id|posting_id|account|ledger_class|amount_cents|ctrl_hash|entry_type|status" > (APP "/out/posting_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!entry_ok(act[ai, "entry_type"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || src[si, "book_ts"] > src[best, "book_ts"] || (src[si, "book_ts"] == src[best, "book_ts"] && si < best)) best = si
        }
        amt = 0 + act[ai, "amount_cents"]
        if (best == 0) { uc++; ua += amt; cls = ""; status = "REJECTED" }
        else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; cls = canon(src[best, "ledger_class"]); status = "POSTED"
        }
        print act[ai, "entry_id"], act[ai, "posting_id"], act[ai, "account"], cls, act[ai, "amount_cents"], act[ai, "ctrl_hash"], act[ai, "entry_type"], status >> (APP "/out/posting_report.csv")
    }
    print "posted_count=" mc > (APP "/out/posting_summary.txt")
    print "posted_amount_cents=" ma >> (APP "/out/posting_summary.txt")
    print "rejected_count=" uc >> (APP "/out/posting_summary.txt")
    print "rejected_amount_cents=" ua >> (APP "/out/posting_summary.txt")
}
AWKEOF

cat > "$T4/environment/src/posting_rules.pli" <<'EOF'
DCL ELIGIBLE_STATE CHAR(12) INIT('BOOKED');
DCL OPEN_BOOK_STATE CHAR(8) INIT('OPEN');
DCL ENTRY_1 CHAR(12) INIT('DEBIT');
DCL ENTRY_2 CHAR(12) INIT('CREDIT');
DCL ENTRY_3 CHAR(12) INIT('ADJUST');
DCL ALIAS_1 CHAR(20) INIT('GL=>GENERAL');
DCL ALIAS_2 CHAR(20) INIT('AP=>PAYABLE');
DCL ALIAS_3 CHAR(20) INIT('AR=>RECEIVABLE');
EOF
cat > "$T4/environment/src/posting_batch.pli" <<'EOF'
/* PL/I general ledger posting normalizer control deck. */
%SET KEY_COMPARE PREFIX5
%SET CONSUME OFF
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF
cat > "$T4/environment/data/journal.psv" <<'EOF'
posting_id|account|amount_cents|ctrl_hash|book_ts|state|ledger_class
PST-10001|400100|15000|ab12|20260612120000|BOOKED|GENERAL
EOF
cat > "$T4/environment/data/postings.psv" <<'EOF'
entry_id|posting_id|account|amount_cents|ctrl_hash|post_ts|entry_type|ledger_class
ENT-1|PST-10001|400100|15000|ab12|20260612120500|DEBIT|GENERAL
EOF
cat > "$T4/environment/config/book_windows.psv" <<'EOF'
account|open_ts|close_ts|state
400100|20260612115900|20260612123000|OPEN
EOF
cat > "$T4/environment/docs/operations.md" <<'EOF'
# General Ledger Posting Normalizer
Normalizes `/app/data/postings.psv` against `/app/data/journal.psv` using PL/I decks.
EOF
echo "posting_id|account" > "$T4/environment/samples/example.psv"

cat > "$T4/steps/milestone_1/instruction.md" <<'EOF'
The general ledger PL/I posting normalizer rejects valid journal matches. Fix `/app/src/posting_batch.pli`, `/app/src/posting_rules.pli`, or the batch harness so `/app/data/postings.psv` normalizes against `/app/data/journal.psv`.

Milestone 1 requires full agreement on `posting_id`, `account`, `amount_cents`, `ctrl_hash`, and `ledger_class`, journal `state` equal to `ELIGIBLE_STATE`, and `entry_type` one of `ENTRY_1`, `ENTRY_2`, or `ENTRY_3`. Each journal row may be consumed once. Preserve entry order. Write `/app/out/posting_report.csv` and `/app/out/posting_summary.txt`.

Status must be exactly `POSTED` or `REJECTED`.
EOF
cat > "$T4/steps/milestone_2/instruction.md" <<'EOF'
The general ledger PL/I posting normalizer rejects valid journal matches. Fix `/app/src/posting_batch.pli`, `/app/src/posting_rules.pli`, or the batch harness.

Milestone 2 keeps milestone 1 rules and enables `ALIAS_*` ledger-class normalization. Emit canonical `ledger_class` for posted rows.
EOF
cat > "$T4/steps/milestone_3/instruction.md" <<'EOF'
The general ledger PL/I posting normalizer rejects valid journal matches. Fix `/app/src/posting_batch.pli`, `/app/src/posting_rules.pli`, or the batch harness.

Milestone 3 keeps prior rules and adds `/app/config/book_windows.psv`. Book and post timestamps must fall inside an open book window per account using `OPEN_BOOK_STATE`. Tie-break on latest `book_ts` then earliest journal row.
EOF

cat > "$T4/steps/milestone_1/tests/test_m1.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def rules(st="BOOKED",ents=("DEBIT","CREDIT","ADJUST")):
    (APP/"src/posting_rules.pli").write_text("\n".join([
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{st}');","DCL OPEN_BOOK_STATE CHAR(8) INIT('OPEN');",
        f"DCL ENTRY_1 CHAR(12) INIT('{ents[0]}');",f"DCL ENTRY_2 CHAR(12) INIT('{ents[1]}');",f"DCL ENTRY_3 CHAR(12) INIT('{ents[2]}');",
        "DCL ALIAS_1 CHAR(20) INIT('GL=>GENERAL');","DCL ALIAS_2 CHAR(20) INIT('AP=>PAYABLE');","DCL ALIAS_3 CHAR(20) INIT('AR=>RECEIVABLE');"])+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    rows=list(csv.DictReader((APP/"out/posting_report.csv").open()))
    summary={k:int(v) for k,v in (l.split("=",1) for l in (APP/"out/posting_summary.txt").read_text().splitlines())}
    return rows,summary
def test_m1():
    rules(st="READY",ents=("OK","WATCH","DONE"))
    w(APP/"data/journal.psv",["posting_id","account","amount_cents","ctrl_hash","book_ts","state","ledger_class"],[
        ["PST-1","400100","10","aa","20260612120000","READY","GENERAL"],
        ["PST-2","400200","20","bb","20260612120100","BAD","PAYABLE"],
        ["PST-3","400300","30","cc","20260612120200","READY","RECEIVABLE"],
    ])
    w(APP/"data/postings.psv",["entry_id","posting_id","account","amount_cents","ctrl_hash","post_ts","entry_type","ledger_class"],[
        ["E1","PST-1","400100","10","aa","20260612120500","OK","GENERAL"],
        ["E2","PST-1","400100","10","aa","20260612120600","OK","GENERAL"],
        ["E3","PST-2","400200","20","bb","20260612120700","OK","PAYABLE"],
        ["E4","PST-3","400300","30","cc","20260612120700","WATCH","RECEIVABLE"],
        ["E5","PST-3","400300","31","cc","20260612120700","WATCH","RECEIVABLE"],
        ["E6","PST-3","400300","30","cc","20260612120700","NOPE","RECEIVABLE"],
    ])
    w(APP/"config/book_windows.psv",["account","open_ts","close_ts","state"],[["400100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows,summary=run()
    assert [r["status"] for r in rows]==["POSTED","REJECTED","REJECTED","POSTED","REJECTED","REJECTED"]
    assert rows[1]["ledger_class"]==""
    assert summary=={"posted_count":2,"posted_amount_cents":40,"rejected_count":4,"rejected_amount_cents":81}
PYEOF

cat > "$T4/steps/milestone_2/tests/test_m2.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/posting_report.csv").open()))
def test_m2():
    (APP/"src/posting_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\nDCL OPEN_BOOK_STATE CHAR(8) INIT('OPEN');\nDCL ENTRY_1 CHAR(12) INIT('GO');\nDCL ENTRY_2 CHAR(12) INIT('CHK');\nDCL ENTRY_3 CHAR(12) INIT('WAIT');\nDCL ALIAS_1 CHAR(20) INIT('gl=>GENERAL');\nDCL ALIAS_2 CHAR(20) INIT('ap=>PAYABLE');\nDCL ALIAS_3 CHAR(20) INIT('ar=>RECEIVABLE');\n")
    w(APP/"data/journal.psv",["posting_id","account","amount_cents","ctrl_hash","book_ts","state","ledger_class"],[["PST-9","400100","99","ff","20260612120000","LIVE","gl"]])
    w(APP/"data/postings.psv",["entry_id","posting_id","account","amount_cents","ctrl_hash","post_ts","entry_type","ledger_class"],[["E9","PST-9","400100","99","ff","20260612120500","go","GENERAL"]])
    w(APP/"config/book_windows.psv",["account","open_ts","close_ts","state"],[["400100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="POSTED" and rows[0]["ledger_class"]=="GENERAL"
PYEOF

cat > "$T4/steps/milestone_3/tests/test_m3.py" <<'PYEOF'
import csv, subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/posting_report.csv").open()))
def test_m3():
    (APP/"src/posting_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\nDCL OPEN_BOOK_STATE CHAR(8) INIT('OPEN');\nDCL ENTRY_1 CHAR(12) INIT('OK');\nDCL ENTRY_2 CHAR(12) INIT('WATCH');\nDCL ENTRY_3 CHAR(12) INIT('DONE');\nDCL ALIAS_1 CHAR(20) INIT('GL=>GENERAL');\nDCL ALIAS_2 CHAR(20) INIT('AP=>PAYABLE');\nDCL ALIAS_3 CHAR(20) INIT('AR=>RECEIVABLE');\n")
    w(APP/"data/journal.psv",["posting_id","account","amount_cents","ctrl_hash","book_ts","state","ledger_class"],[
        ["PST-A","400100","10","h1","20260612120000","OPEN","GENERAL"],
        ["PST-A","400100","10","h1","20260612120100","OPEN","GENERAL"],
    ])
    w(APP/"data/postings.psv",["entry_id","posting_id","account","amount_cents","ctrl_hash","post_ts","entry_type","ledger_class"],[["E-W","PST-A","400100","10","h1","20260612120500","OK","GENERAL"]])
    w(APP/"config/book_windows.psv",["account","open_ts","close_ts","state"],[["400100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    assert run()[0]["status"]=="POSTED"
    w(APP/"data/postings.psv",["entry_id","posting_id","account","amount_cents","ctrl_hash","post_ts","entry_type","ledger_class"],[["E-X","PST-A","400100","10","h1","20260612130000","OK","GENERAL"]])
    assert run()[0]["status"]=="REJECTED"
PYEOF

for m in 1 2 3; do write_test_sh "$m" "test_m${m}.py" "$T4"; done
B='/* PL/I general ledger posting normalizer control deck. */'
write_solve_chain "$T4" 1 "cat > /app/src/posting_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF"
write_solve_chain "$T4" 2 "cat > /app/src/posting_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
EOF"
write_solve_chain "$T4" 3 "cat > /app/src/posting_batch.pli <<'EOF'
$B
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
EOF"
echo "Created $T4"
