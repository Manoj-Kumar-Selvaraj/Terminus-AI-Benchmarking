#!/usr/bin/env bash
# Ports previously-skipped v1/v2 concepts into PL/I batch tasks.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT/pli-orbit-downlink-frame-auditor"

dockerfile() {
  cat > "$1/environment/Dockerfile" <<'EOF'
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

task_toml() {
  local dir="$1" tags="$2"
  sed "s/tags = .*/tags = [$tags]/" "$TEMPLATE/task.toml" > "$dir/task.toml"
}

write_test_sh() {
  local m="$1" py="$2" dir="$3"
  cp "$TEMPLATE/steps/milestone_${m}/tests/test.sh" "$dir/steps/milestone_${m}/tests/test.sh"
  sed -i "s/test_m[0-9]\\.py/${py}/" "$dir/steps/milestone_${m}/tests/test.sh"
}

write_solves() {
  local dir="$1" batch_file="$2" comment="$3"
  for m in 1 2 3; do
    local alias=OFF win=OFF
    [[ "$m" -ge 2 ]] && alias=ON
    [[ "$m" -ge 3 ]] && win=ON
    cat > "$dir/steps/milestone_${m}/solution/solve${m}.sh" <<EOF
#!/bin/bash
set -euo pipefail
cat > /app/src/${batch_file} <<'PLI'
/* ${comment} batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ${alias}
%SET WINDOW_MODE ${win}
PLI
/app/scripts/run_batch.sh
EOF
    chmod +x "$dir/steps/milestone_${m}/solution/solve${m}.sh"
  done
  cat > "$dir/steps/milestone_1/solution/solve.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"
EOF
  chmod +x "$dir/steps/milestone_1/solution/solve.sh"
  for m in 2 3; do
    cat > "$dir/steps/milestone_${m}/solution/solve.sh" <<EOF
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
bash "\$SCRIPT_DIR/solve${m}.sh"
EOF
    chmod +x "$dir/steps/milestone_${m}/solution/solve.sh"
  done
}

pad_env() {
  local dir="$1"
  for n in 04 05 06 07 08 09 10; do
    echo "Operational evidence note $n." > "$dir/environment/docs/audit_support_${n}.md"
  done
  mkdir -p "$dir/environment/evidence"
  echo "2026-06-12T12:00:00Z incident trace" > "$dir/environment/evidence/incident_trace.log"
  cat > "$dir/environment/docs/batch_contract.md" <<'EOF'
# Batch Contract
Edit `/app/src/*_rules.pli` and `/app/src/*_batch.pli` only. The gawk harness is fixed.
EOF
  cat > "$dir/environment/config/defaults.psv" <<'EOF'
setting|value
batch_mode|production
EOF
  cat > "$dir/environment/.dockerignore" <<'EOF'
out/
build/
.git
.gitignore
**/__pycache__/
**/*.pyc
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/node_modules/
EOF
}

# Args: name tags rules batch awk src_psv act_psv win_psv win_key
#       keys emit accept reject mc ma rc ra amt
#       eligible open r1 r2 r3 alias1 alias2 alias3
#       report summary src_ts act_ts reason_col emit_col
create_task() {
  local NAME="$1" TAGS="$2" RULES="$3" BATCH="$4" AWK="$5"
  local SRC_PSV="$6" ACT_PSV="$7" WIN_PSV="$8" WIN_KEY="$9"
  local KEYS="${10}" EMIT="${11}" ACCEPT="${12}" REJECT="${13}"
  local MC="${14}" MA="${15}" RC="${16}" RA="${17}" AMT="${18}"
  local ELIG="${19}" OPEN="${20}" R1="${21}" R2="${22}" R3="${23}"
  local A1="${24}" A2="${25}" A3="${26}"
  local REPORT="${27}" SUMMARY="${28}" SRC_TS="${29}" ACT_TS="${30}"
  local REASON_COL="${31}" EMIT_COL="${32}" COMMENT="${33}"
  local DIR="$ROOT/$NAME"

  rm -rf "$DIR"
  mkdir -p "$DIR/steps"/{milestone_1,milestone_2,milestone_3}/{tests,solution}
  mkdir -p "$DIR/environment"/{scripts,src,data,config,docs,samples}

  task_toml "$DIR" "$TAGS"
  dockerfile "$DIR"
  pad_env "$DIR"

  cat > "$DIR/environment/scripts/run_batch.sh" <<EOF
#!/bin/bash
set -euo pipefail
gawk -f /app/scripts/${AWK}
EOF
  chmod +x "$DIR/environment/scripts/run_batch.sh"

  # Build awk from template with substitutions
  sed -e "s/wire_rules\\.pli/${RULES}/g" \
      -e "s/wire_batch\\.pli/${BATCH}/g" \
      -e "s/data\\/clearing\\.psv/data\\/${SRC_PSV}/g" \
      -e "s/data\\/claims\\.psv/data\\/${ACT_PSV}/g" \
      -e "s/config\\/clearing_windows\\.psv/config\\/${WIN_PSV}/g" \
      -e "s/win\\[wi, \"account\"\\]/win[wi, \"${WIN_KEY}\"]/g" \
      -e "s/src\\[si, \"account\"\\]/src[si, \"${WIN_KEY}\"]/g" \
      -e "s/wire_id account amount_cents rail_code branch_id/${KEYS}/g" \
      -e "s/cleared_amount_cents/${MA}/g" \
      -e "s/returned_amount_cents/${RA}/g" \
      -e "s/cleared_count/${MC}/g" \
      -e "s/returned_count/${RC}/g" \
      -e "s/amount_cents/${AMT}/g" \
      -e "s/rail_code/${EMIT}/g" \
      -e "s/CLEARED/${ACCEPT}/g" \
      -e "s/RETURNED/${REJECT}/g" \
      -e "s/posted_ts/${SRC_TS}/g" \
      -e "s/claim_ts/${ACT_TS}/g" \
      -e "s/reason_code/${REASON_COL}/g" \
      -e "s/wire_report\\.csv/${REPORT}/g" \
      -e "s/wire_summary\\.txt/${SUMMARY}/g" \
      -e "s/OPEN_CLEAR_STATE/${OPEN}/g" \
      "$TEMPLATE/environment/scripts/pli_wire.awk" > "$DIR/environment/scripts/${AWK}"

  P_A=$(echo "$MC" | sed 's/_count$//')
  P_R=$(echo "$RC" | sed 's/_count$//')
  sed -i "s/${P_A}_${AMT}/${MA}/g; s/${P_R}_${AMT}/${RA}/g" "$DIR/environment/scripts/${AWK}"

  # Fix first key for PREFIX5 - use first field from KEYS
  local K1
  K1=$(echo "$KEYS" | awk '{print $1}')
  K2=$(echo "$KEYS" | awk '{print $2}')
  K5=$(echo "$KEYS" | awk '{print $5}')
  sed -i \
    -e "s/substr(src\\[si, \"wire_id\"\\]/substr(src[si, \"${K1}\"]/g" \
    -e "s/substr(act\\[ai, \"wire_id\"\\]/substr(act[ai, \"${K1}\"]/g" \
    -e "s/act\\[ai, \"wire_id\"\\]/act[ai, \"${K1}\"]/g" \
    -e "s/act\\[ai, \"account\"\\]/act[ai, \"${K2}\"]/g" \
    -e "s/act\\[ai, \"branch_id\"\\]/act[ai, \"${K5}\"]/g" \
    -e "s/\"claim_id|wire_id|account|branch_id|rail_code|amount_cents|reason_code|status\"/\"claim_id|${K1}|${K2}|${K5}|${EMIT}|${AMT}|${REASON_COL}|status\"/g" \
    -e "s/claim_id|wire_id|account|branch_id|rail_code|amount_cents|reason_code|status/claim_id|${K1}|${K2}|${K5}|${EMIT}|${AMT}|${REASON_COL}|status/g" \
    "$DIR/environment/scripts/${AWK}"

  cat > "$DIR/environment/src/${RULES}" <<EOF
DCL ELIGIBLE_STATE CHAR(12) INIT('POSTED');
DCL ${OPEN} CHAR(8) INIT('OPEN');
DCL REASON_1 CHAR(12) INIT('${R1}');
DCL REASON_2 CHAR(12) INIT('${R2}');
DCL REASON_3 CHAR(12) INIT('${R3}');
DCL ALIAS_1 CHAR(20) INIT('${A1}');
DCL ALIAS_2 CHAR(20) INIT('${A2}');
DCL ALIAS_3 CHAR(20) INIT('${A3}');
EOF

  cat > "$DIR/environment/src/${BATCH}" <<EOF
/* ${COMMENT} batch control deck */
%SET KEY_COMPARE PREFIX5
%SET CONSUME OFF
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF

  local K1 K2 K3 K4 K5
  read -r K1 K2 K3 K4 K5 <<< "$KEYS"
  cat > "$DIR/environment/data/${SRC_PSV}" <<EOF
${K1}|${K2}|${K3}|${K4}|${K5}|${SRC_TS}|state|kind_code
BATCH-10001|991100|50000|FED|NYC|20260612120000|POSTED|TM
EOF
  cat > "$DIR/environment/data/${ACT_PSV}" <<EOF
claim_id|${K1}|${K2}|${K3}|${K4}|${ACT_TS}|${REASON_COL}|${K5}
CLM-1|BATCH-10001|991100|50000|FED|20260612120500|${R1}|NYC
EOF
  cat > "$DIR/environment/config/${WIN_PSV}" <<EOF
${WIN_KEY}|open_ts|close_ts|state
991100|20260612115900|20260612123000|OPEN
EOF
  echo "${K1}|${K2}" > "$DIR/environment/samples/example.psv"
  echo "# ${NAME}" > "$DIR/environment/docs/operations.md"

  write_solves "$DIR" "$BATCH" "$COMMENT"
  for m in 1 2 3; do write_test_sh "$m" "test_m${m}.py" "$DIR"; done

  # Generate tests from treasury pattern
  local ID1 ID2
  ID1=$(echo "$ACT_PSV" | sed 's/.psv//' | cut -c1-3 | tr 'a-z' 'A-Z')
  [[ -z "$ID1" ]] && ID1="ACT"
  python3 - "$DIR" "$NAME" "$SRC_PSV" "$ACT_PSV" "$WIN_PSV" "$WIN_KEY" "$KEYS" "$EMIT" "$ACCEPT" "$REJECT" "$MC" "$MA" "$RC" "$RA" "$AMT" "$REPORT" "$SUMMARY" "$REASON_COL" "$EMIT_COL" "$SRC_TS" "$ACT_TS" "$OPEN" "$R1" "$A1" <<'PY'
import sys
from pathlib import Path

dir_, *rest = sys.argv[1:]
(NAME, SRC_PSV, ACT_PSV, WIN_PSV, WIN_KEY, KEYS, EMIT, ACCEPT, REJECT,
 MC, MA, RC, RA, AMT, REPORT, SUMMARY, REASON_COL, EMIT_COL, SRC_TS, ACT_TS,
 OPEN, R1, A1) = rest
keys = KEYS.split()
K1, K2, K3, K4, K5 = (keys + ["x"] * 5)[:5]
base = Path(dir_)

m1 = f'''import csv
import subprocess
from pathlib import Path
APP = Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\\n"+"\\n".join("|".join(x) for x in r)+"\\n")
def rules(st="POSTED",rs=("{R1}","CHK","DONE")):
    rules_path = list((APP/"src").glob("*_rules.pli"))[0]
    rules_path.write_text("\\n".join([
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{{st}}');", "DCL {OPEN} CHAR(8) INIT('OPEN');",
        f"DCL REASON_1 CHAR(12) INIT('{{rs[0]}}');", "DCL REASON_2 CHAR(12) INIT('WATCH');", "DCL REASON_3 CHAR(12) INIT('DONE');",
        "DCL ALIAS_1 CHAR(20) INIT('{A1}');", "DCL ALIAS_2 CHAR(20) INIT('B=>BETA');", "DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');"])+"\\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = APP/"out"/"{REPORT}"
    rows=list(csv.DictReader(report.open(), delimiter="|"))
    summary={{k:int(v) for k,v in (line.split("=", 1) for line in (APP/"out"/"{SUMMARY}").read_text().splitlines())}}
    return rows,summary
def test_m1():
    rules(st="LIVE",rs=("OK","WATCH","DONE"))
    w(APP/"data"/"{SRC_PSV}",["{K1}","{K2}","{K3}","{K4}","{K5}","{SRC_TS}","state","kind_code"],[
        ["R-1","991100","10","FED","NYC","20260612120000","LIVE","TM"],
        ["R-2","991200","20","ACH","NYC","20260612120100","BAD","TM"],
        ["R-3","991300","30","SWIFT","BOS","20260612120200","LIVE","TM"],
    ])
    w(APP/"data"/"{ACT_PSV}",["claim_id","{K1}","{K2}","{K3}","{K4}","{ACT_TS}","{REASON_COL}","{K5}"],[
        ["C1","R-1","991100","10","FED","20260612120500","OK","NYC"],
        ["C2","R-1","991100","10","FED","20260612120600","OK","NYC"],
        ["C3","R-2","991200","20","ACH","20260612120700","OK","NYC"],
        ["C4","R-3","991300","30","SWIFT","20260612120700","WATCH","BOS"],
        ["C5","R-3","991300","31","SWIFT","20260612120700","WATCH","BOS"],
        ["C6","R-3","991300","30","SWIFT","20260612120700","NOPE","BOS"],
    ])
    w(APP/"config"/"{WIN_PSV}",["{WIN_KEY}","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows,summary=run()
    assert [r["status"] for r in rows]==["{ACCEPT}","{REJECT}","{REJECT}","{ACCEPT}","{REJECT}","{REJECT}"]
    assert rows[1]["{EMIT}"]==""
    assert summary=={{"{MC}":2,"{MA}":40,"{RC}":4,"{RA}":91}}
'''
m2 = f'''import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\\n"+"\\n".join("|".join(x) for x in r)+"\\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out"/"{REPORT}").open(), delimiter="|"))
def test_m2():
    rules_path = list((APP/"src").glob("*_rules.pli"))[0]
    rules_path.write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\\nDCL {OPEN} CHAR(8) INIT('OPEN');\\nDCL REASON_1 CHAR(12) INIT('GO');\\nDCL REASON_2 CHAR(12) INIT('CHK');\\nDCL REASON_3 CHAR(12) INIT('WAIT');\\nDCL ALIAS_1 CHAR(20) INIT('f=>FED');\\nDCL ALIAS_2 CHAR(20) INIT('a=>ACH');\\nDCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');\\n")
    if "{EMIT}" == "{K4}":
        m2_src=["R-9","991100","99","f","NYC","20260612120000","LIVE","tm"]
        m2_act=["C9","R-9","991100","99","FED","20260612120500","go","NYC"]
    else:
        m2_src=["R-9","991100","99","FED","f","20260612120000","LIVE","tm"]
        m2_act=["C9","R-9","991100","99","FED","20260612120500","go","FED"]
    w(APP/"data"/"{SRC_PSV}",["{K1}","{K2}","{K3}","{K4}","{K5}","{SRC_TS}","state","kind_code"],[m2_src])
    w(APP/"data"/"{ACT_PSV}",["claim_id","{K1}","{K2}","{K3}","{K4}","{ACT_TS}","{REASON_COL}","{K5}"],[m2_act])
    w(APP/"config"/"{WIN_PSV}",["{WIN_KEY}","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="{ACCEPT}" and rows[0]["{EMIT}"]=="FED"
'''
m3 = f'''import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\\n"+"\\n".join("|".join(x) for x in r)+"\\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out"/"{REPORT}").open(), delimiter="|"))
def test_m3():
    rules_path = list((APP/"src").glob("*_rules.pli"))[0]
    rules_path.write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\\nDCL {OPEN} CHAR(8) INIT('OPEN');\\nDCL REASON_1 CHAR(12) INIT('OK');\\nDCL REASON_2 CHAR(12) INIT('WATCH');\\nDCL REASON_3 CHAR(12) INIT('DONE');\\nDCL ALIAS_1 CHAR(20) INIT('{A1}');\\nDCL ALIAS_2 CHAR(20) INIT('A=>ACH');\\nDCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');\\n")
    w(APP/"data"/"{SRC_PSV}",["{K1}","{K2}","{K3}","{K4}","{K5}","{SRC_TS}","state","kind_code"],[
        ["R-A","991100","10","FED","NYC","20260612120000","OPEN","TM"],
        ["R-A","991100","10","FED","NYC","20260612120100","OPEN","TM"],
    ])
    w(APP/"data"/"{ACT_PSV}",["claim_id","{K1}","{K2}","{K3}","{K4}","{ACT_TS}","{REASON_COL}","{K5}"],[["C-W","R-A","991100","10","FED","20260612120500","OK","NYC"]])
    w(APP/"config"/"{WIN_PSV}",["{WIN_KEY}","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    assert run()[0]["status"]=="{ACCEPT}"
    w(APP/"data"/"{ACT_PSV}",["claim_id","{K1}","{K2}","{K3}","{K4}","{ACT_TS}","{REASON_COL}","{K5}"],[["C-X","R-A","991100","10","FED","20260612130000","OK","NYC"]])
    assert run()[0]["status"]=="{REJECT}"
'''
for i, content in enumerate([m1, m2, m3], 1):
    (base / f"steps/milestone_{i}/tests/test_m{i}.py").write_text(content)
PY

  # Instructions
  for m in 1 2 3; do
    local extra=""
    [[ "$m" -ge 2 ]] && extra="Milestone ${m} keeps prior rules and enables ALIAS_* normalization."
    [[ "$m" -ge 3 ]] && extra="Milestone ${m} keeps prior rules and adds /app/config/${WIN_PSV} window gates using ${OPEN}."
    [[ "$m" -eq 1 ]] && extra="Milestone 1 requires full-key match, ELIGIBLE_STATE gate, consumption once, and ${REASON_COL} in REASON_1/2/3."
    cat > "$DIR/steps/milestone_${m}/instruction.md" <<EOF
The ${COMMENT} PL/I batch is too loose. Fix \`/app/src/${RULES}\`, \`/app/src/${BATCH}\`, or the batch harness.

${extra}

Status must be exactly \`${ACCEPT}\` or \`${REJECT}\`.
EOF
  done

  echo "Created $NAME"
}

create_task "pli-retail-batch-trailer-reconciler" \
  '"pli", "batch", "banking", "retail"' \
  "trailer_rules.pli" "trailer_batch.pli" "pli_trailer.awk" \
  "batches.psv" "trailer_claims.psv" "settlement_windows.psv" "account_no" \
  "batch_id account_no net_cents dc_flag branch_id" "dc_flag" "BALANCED" "REJECTED" \
  "balanced_count" "balanced_amount_cents" "rejected_count" "rejected_amount_cents" "net_cents" \
  "POSTED" "OPEN_SETTLE_STATE" "SETTLE" "RECALL" "ADJUST" \
  "D=>DEBIT" "C=>CREDIT" "X=>XFER" \
  "trailer_report.csv" "trailer_summary.txt" "posted_ts" "claim_ts" "reason_code" "dc_flag" \
  "retail batch trailer reconciler"

# 2 insurance
create_task "pli-insurance-premium-surcharge-adjudicator" \
  '"pli", "batch", "insurance", "premium"' \
  "premium_rules.pli" "premium_batch.pli" "pli_premium.awk" \
  "policies.psv" "adjustments.psv" "fiscal_windows.psv" "account_no" \
  "policy_id account_no premium_cents risk_code branch_id" "risk_code" "VALID" "INVALID" \
  "valid_count" "valid_amount_cents" "invalid_count" "invalid_amount_cents" "premium_cents" \
  "ACTIVE" "OPEN_FISCAL_STATE" "RATE" "REVIEW" "HOLD" \
  "R3=>HIGH" "R2=>MID" "R1=>LOW" \
  "premium_report.csv" "premium_summary.txt" "ingest_ts" "adj_ts" "opcode" "risk_code" \
  "insurance premium surcharge adjudicator"

# 3 mainframe tape
create_task "pli-mainframe-tape-record-integrity-auditor" \
  '"pli", "batch", "mainframe", "tape"' \
  "tape_rules.pli" "tape_batch.pli" "pli_tape.awk" \
  "tape_catalog.psv" "tape_audits.psv" "mount_windows.psv" "volume_id" \
  "record_id volume_id length_hash block_no reel_id" "block_no" "VERIFIED" "CORRUPT" \
  "verified_count" "verified_blocks" "corrupt_count" "corrupt_blocks" "length_hash" \
  "MOUNTED" "OPEN_MOUNT_STATE" "SCAN" "REPAIR" "SKIP" \
  "V1=>VOL1" "V2=>VOL2" "T=>TAPE" \
  "tape_report.csv" "tape_summary.txt" "recv_ts" "audit_ts" "verdict_code" "block_no" \
  "mainframe tape record integrity auditor"

# 4 semantic payload
create_task "pli-canonical-payload-semantic-matcher" \
  '"pli", "batch", "semantic", "payload"' \
  "semantic_rules.pli" "semantic_batch.pli" "pli_semantic.awk" \
  "expected.psv" "actual.psv" "compare_windows.psv" "schema_id" \
  "field_id schema_id payload_hash tolerance_key segment_id" "segment_id" "EQUAL" "DIFFER" \
  "equal_count" "equal_fields" "differ_count" "differ_fields" "payload_hash" \
  "READY" "OPEN_COMPARE_STATE" "MATCH" "TOLERATE" "IGNORE" \
  "S=>STRING" "N=>NUMBER" "B=>BOOL" \
  "semantic_report.csv" "semantic_summary.txt" "recv_ts" "check_ts" "mode_code" "segment_id" \
  "canonical payload semantic matcher"

# 5 multicurrency ledger
create_task "pli-multicurrency-ledger-clearing-processor" \
  '"pli", "batch", "ledger", "multicurrency"' \
  "ledger_rules.pli" "ledger_batch.pli" "pli_ledger.awk" \
  "ledger.psv" "postings.psv" "fx_windows.psv" "account_id" \
  "txn_id account_id amount_cents currency_code desk_id" "currency_code" "CLEARED" "HELD" \
  "cleared_count" "cleared_amount_cents" "held_count" "held_amount_cents" "amount_cents" \
  "OPEN" "OPEN_FX_STATE" "POST" "TRANSFER" "FEE" \
  "USD=>DOLLAR" "EUR=>EURO" "GBP=>STERLING" \
  "ledger_report.csv" "ledger_summary.txt" "book_ts" "post_ts" "entry_type" "currency_code" \
  "multicurrency ledger clearing processor"

# 6 workload manifest
create_task "pli-workload-manifest-consistency-auditor" \
  '"pli", "batch", "kubernetes", "manifest"' \
  "manifest_rules.pli" "manifest_batch.pli" "pli_manifest.awk" \
  "manifests.psv" "rollout_checks.psv" "rollout_windows.psv" "namespace" \
  "workload_id namespace selector_label port_name probe_path" "port_name" "CONSISTENT" "DRIFTED" \
  "consistent_count" "consistent_checks" "drifted_count" "drifted_checks" "selector_label" \
  "READY" "OPEN_ROLLOUT_STATE" "SYNC" "PATCH" "ROLL" \
  "8080=>HTTP" "http=>HTTP" "app=>WORKLOAD" \
  "manifest_report.csv" "manifest_summary.txt" "applied_ts" "check_ts" "check_code" "port_name" \
  "workload manifest consistency auditor"

# 7 infrastructure drift
create_task "pli-infrastructure-state-drift-adjudicator" \
  '"pli", "batch", "infrastructure", "drift"' \
  "drift_rules.pli" "drift_batch.pli" "pli_drift.awk" \
  "ideal.psv" "observed.psv" "audit_windows.psv" "resource_group" \
  "resource_id resource_group attr_hash module_name region_code" "module_name" "ALIGNED" "DRIFTED" \
  "aligned_count" "aligned_resources" "drifted_count" "drifted_resources" "attr_hash" \
  "ACTIVE" "OPEN_AUDIT_STATE" "MATCH" "DRIFT" "IGNORE" \
  "rg=>PROD" "mod=>ROOT" "aws=>CLOUD" \
  "drift_report.csv" "drift_summary.txt" "ideal_ts" "scan_ts" "scan_code" "module_name" \
  "infrastructure state drift adjudicator"

# 8 privilege mandate
create_task "pli-privilege-mandate-sandbox-classifier" \
  '"pli", "batch", "security", "sandbox"' \
  "mandate_rules.pli" "mandate_batch.pli" "pli_mandate.awk" \
  "mandates.psv" "sandbox_audits.psv" "sandbox_windows.psv" "service_id" \
  "mandate_id service_id cap_token payload_hash sandbox_class" "sandbox_class" "AUTHORIZED" "DENIED" \
  "authorized_count" "authorized_mandates" "denied_count" "denied_mandates" "cap_token" \
  "ARMED" "OPEN_SANDBOX_STATE" "GRANT" "AUDIT" "REVOKE" \
  "dac=>DAC_OVERRIDE" "chown=>CHOWN" "fowner=>FOWNER" \
  "mandate_report.csv" "mandate_summary.txt" "recv_ts" "audit_ts" "verdict_code" "sandbox_class" \
  "privilege mandate sandbox classifier"

# 9 numeric rollup
create_task "pli-numeric-directive-rollup-processor" \
  '"pli", "batch", "rollup", "numeric"' \
  "rollup_rules.pli" "rollup_batch.pli" "pli_rollup.awk" \
  "directives.psv" "accumulators.psv" "rollup_windows.psv" "stream_id" \
  "line_id stream_id value_cents base_radix segment_id" "segment_id" "ROLLED" "SKIPPED" \
  "rolled_count" "rolled_total_cents" "skipped_count" "skipped_total_cents" "value_cents" \
  "LIVE" "OPEN_ROLLUP_STATE" "ADD" "SUB" "BASE" \
  "hex=>HEX" "dec=>DEC" "oct=>OCT" \
  "rollup_report.csv" "rollup_summary.txt" "ingest_ts" "rollup_ts" "opcode" "segment_id" \
  "numeric directive rollup processor"

echo "All skipped-category PL/I ports generated."
