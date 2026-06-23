#!/usr/bin/env bash
# Generates four PL/I-only ported tasks (no agent-facing Python).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

write_common_dockerfile() {
  local task_dir="$1"
  cat > "$task_dir/environment/Dockerfile" <<'EOF'
FROM python:3.11-slim-bookworm@sha256:cd67330292a51e2963156f74ff340455d66b2172e9190e99f40dff9357471177

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gawk tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

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

write_dockerignore() {
  local task_dir="$1"
  cat > "$task_dir/environment/.dockerignore" <<'EOF'
out/
build/
__pycache__/
*.pyc
EOF
}

write_task_toml() {
  local task_dir="$1"
  local tags="$2"
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
  local milestone="$1"
  local test_py="$2"
  local dir="$3/steps/milestone_${milestone}/tests"
  cat > "$dir/test.sh" <<EOF
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "\$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/${test_py} -rA

if [ \$? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
EOF
  chmod +x "$dir/test.sh"
}

write_solve_chain() {
  local task_dir="$1"
  local milestone="$2"
  local solve_body="$3"
  local sol_dir="$task_dir/steps/milestone_${milestone}/solution"
  mkdir -p "$sol_dir"
  cat > "$sol_dir/solve${milestone}.sh" <<EOF
#!/bin/bash
set -euo pipefail
$solve_body
/app/scripts/run_batch.sh
EOF
  chmod +x "$sol_dir/solve${milestone}.sh"
  if [[ "$milestone" == "1" ]]; then
    cat > "$sol_dir/solve.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"
EOF
  else
    cat > "$sol_dir/solve.sh" <<EOF
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
bash "\$SCRIPT_DIR/solve${milestone}.sh"
EOF
  fi
  chmod +x "$sol_dir/solve.sh"
}

# ---------------------------------------------------------------------------
# Task 1: pli-orbit-downlink-frame-auditor
# ---------------------------------------------------------------------------
T1="pli-orbit-downlink-frame-auditor"
rm -rf "$T1"
mkdir -p "$T1/environment"/{scripts,src,data,config,docs,samples}
mkdir -p "$T1/steps"/{milestone_1,milestone_2,milestone_3}/{tests,solution}

write_task_toml "$T1" '"pli", "batch", "telemetry", "reconciliation"'
write_common_dockerfile "$T1"
write_dockerignore "$T1"

cat > "$T1/environment/scripts/run_batch.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
gawk -f /app/scripts/pli_audit.awk
EOF
chmod +x "$T1/environment/scripts/run_batch.sh"

cat > "$T1/environment/scripts/pli_audit.awk" <<'AWKEOF'
BEGIN {
    KEY_COMPARE = "PREFIX5"
    CONSUME = "OFF"
    ALIAS_MODE = "OFF"
    WINDOW_MODE = "OFF"
    APP = "/app"
    FS = OFS = "|"
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, upper, name, i, val, a, b) {
    while ((getline line < (APP "/src/audit_rules.pli")) > 0) {
        raw = trim(line); upper = toupper(raw)
        if (upper !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); val = trim(val)
        rules[name] = val
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); a = up(parts[1]); b = up(parts[2])
            aliases[a] = b; aliases[b] = b
        }
    }
    close(APP "/src/audit_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/audit_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[1] == "%SET" && length(parts) >= 3) {
            if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
            else if (parts[2] == "CONSUME") CONSUME = parts[3]
            else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
            else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
        }
    }
    close(APP "/src/audit_batch.pli")
}
function canon(field,    k) {
    k = up(field)
    if (ALIAS_MODE == "ON" && (k in aliases)) return aliases[k]
    return k
}
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function win_ok(src, act,    w, o, c) {
    if (WINDOW_MODE != "ON") return 1
    st = src["recv_ts"]; at = act["audit_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        w = windows[wi]
        if (w["craft_id"] != src["craft_id"]) continue
        if (up(w["state"]) != up(rules["OPEN_PASS_STATE"])) continue
        o = w["open_ts"]; c = w["close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function keys_ok(src, act,    f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src["frame_id"], 1, 5) == substr(act["frame_id"], 1, 5) \
            && src["payload_hash"] == act["payload_hash"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(src[f]) != canon(act[f])) return 0
    }
    return 1
}
function read_psv(path, nrec,    line, nh, i, f) {
    delete hdr; delete rows
    if ((getline line < path) <= 0) { close(path); return }
    nh = split(line, hdr, "|")
    nrec = 0
    while ((getline line < path) > 0) {
        nrec++
        split(line, fields, "|")
        for (i = 1; i <= nh; i++) rows[nrec, hdr[i]] = trim(fields[i])
    }
    close(path)
}
END {
    split("frame_id craft_id channel payload_hash service_class", key_fields, " ")
    nkeys = 5
    load_rules(); load_batch()
    eligible = up(rules["ELIGIBLE_STATE"])
    split(up(rules["VERDICT_A"]) "|" up(rules["VERDICT_B"]) "|" up(rules["VERDICT_C"]), verdicts, "|")
    read_psv(APP "/data/catalog.psv", scount)
    read_psv(APP "/data/audits.psv", acount)
    wcount = 0
    if (WINDOW_MODE == "ON") {
        delete windows
        if ((getline line < (APP "/config/pass_windows.psv")) > 0) {
            wh = split(line, whdr, "|")
            while ((getline line < (APP "/config/pass_windows.psv")) > 0) {
                wcount++
                split(line, wf, "|")
                for (wi = 1; wi <= wh; wi++) windows[wcount, whdr[wi]] = trim(wf[wi])
            }
        }
        close(APP "/config/pass_windows.psv")
    }
    for (si = 1; si <= scount; si++) used[si] = 0
    mc = uc = ma = ua = 0
    print "audit_id", "frame_id", "craft_id", "channel", "service_class", "payload_hash", "verdict_code", "status" > (APP "/out/audit_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        act_craft = canon(audits[ai, "craft_id"])
        act_chan = canon(audits[ai, "channel"])
        act_class = canon(audits[ai, "service_class"])
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            src = si
            if (!keys_ok(catalog, audits[ai])) continue
            if (up(catalog[si, "state"]) != eligible) continue
            vcode = up(audits[ai, "verdict_code"])
            okv = 0
            for (vi = 1; vi <= 3; vi++) if (vcode == verdicts[vi]) { okv = 1; break }
            if (!okv) continue
            if (canon(catalog[si, "craft_id"]) != act_craft) continue
            if (canon(catalog[si, "channel"]) != act_chan) continue
            if (canon(catalog[si, "service_class"]) != act_class) continue
            if (!win_ok(catalog[si], audits[ai])) continue
            if (best == 0 || catalog[si, "recv_ts"] > catalog[best, "recv_ts"] \
                || (catalog[si, "recv_ts"] == catalog[best, "recv_ts"] && si < best)) best = si
        }
        amt = 0 + audits[ai, "payload_hash"]
        if (best == 0) {
            uc++; ua += 1; cls = ""; status = "REJECTED"
        } else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += 1; cls = canon(catalog[best, "service_class"]); status = "ACCEPTED"
        }
        print audits[ai, "audit_id"], audits[ai, "frame_id"], audits[ai, "craft_id"], \
            audits[ai, "channel"], cls, audits[ai, "payload_hash"], audits[ai, "verdict_code"], status \
            >> (APP "/out/audit_report.csv")
    }
    print "matched_count=" mc > (APP "/out/audit_summary.txt")
    print "matched_frames=" ma >> (APP "/out/audit_summary.txt")
    print "rejected_count=" uc >> (APP "/out/audit_summary.txt")
    print "rejected_frames=" ua >> (APP "/out/audit_summary.txt")
}
AWKEOF

# Fix awk: keys_ok used wrong array access - rewrite pli_audit.awk properly
cat > "$T1/environment/scripts/pli_audit.awk" <<'AWKEOF'
BEGIN {
    KEY_COMPARE = "PREFIX5"
    CONSUME = "OFF"
    ALIAS_MODE = "OFF"
    WINDOW_MODE = "OFF"
    APP = "/app"
    FS = OFS = "|"
    split("frame_id craft_id channel payload_hash service_class", key_fields, " ")
    nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/audit_rules.pli")) > 0) {
        raw = trim(line)
        if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); val = trim(val)
        rules[name] = val
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>")
            aliases[up(parts[1])] = up(parts[2])
            aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/audit_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/audit_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[1] == "%SET" && length(parts) >= 3) {
            if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
            else if (parts[2] == "CONSUME") CONSUME = parts[3]
            else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
            else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
        }
    }
    close(APP "/src/audit_batch.pli")
}
function canon(field,    k) {
    k = up(field)
    return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k)
}
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(cat[si, "frame_id"], 1, 5) == substr(aud[ai, "frame_id"], 1, 5) \
            && cat[si, "payload_hash"] == aud[ai, "payload_hash"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(cat[si, f]) != canon(aud[ai, f])) return 0
    }
    return 1
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = cat[si, "recv_ts"]; at = aud[ai, "audit_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "craft_id"] != cat[si, "craft_id"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_PASS_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function verdict_ok(vcode,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(vcode) == up(rules["VERDICT_" substr("ABC", vi, 1)]) ) return 1
    return 0
}
END {
    load_rules(); load_batch()
    eligible = up(rules["ELIGIBLE_STATE"])
    scount = 0
    while ((getline line < (APP "/data/catalog.psv")) > 0) {
        if (scount == 0) { split(line, chdr, "|"); continue }
        scount++
        split(line, cf, "|")
        for (ci = 1; ci <= length(chdr); ci++) cat[scount, chdr[ci]] = trim(cf[ci])
    }
    close(APP "/data/catalog.psv")
    acount = 0
    while ((getline line < (APP "/data/audits.psv")) > 0) {
        if (acount == 0) { split(line, ahdr, "|"); continue }
        acount++
        split(line, af, "|")
        for (ai2 = 1; ai2 <= length(ahdr); ai2++) aud[acount, ahdr[ai2]] = trim(af[ai2])
    }
    close(APP "/data/audits.psv")
    wcount = 0
    if (WINDOW_MODE == "ON") {
        while ((getline line < (APP "/config/pass_windows.psv")) > 0) {
            if (wcount == 0) { split(line, whdr, "|"); continue }
            wcount++
            split(line, wf, "|")
            for (wi2 = 1; wi2 <= length(whdr); wi2++) win[wcount, whdr[wi2]] = trim(wf[wi2])
        }
        close(APP "/config/pass_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "audit_id", "frame_id", "craft_id", "channel", "service_class", "payload_hash", "verdict_code", "status" > (APP "/out/audit_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(cat[si, "state"]) != eligible) continue
            if (!verdict_ok(aud[ai, "verdict_code"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || cat[si, "recv_ts"] > cat[best, "recv_ts"] \
                || (cat[si, "recv_ts"] == cat[best, "recv_ts"] && si < best)) best = si
        }
        if (best == 0) {
            uc++; ua++; cls = ""; status = "REJECTED"
        } else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma++; cls = canon(cat[best, "service_class"]); status = "ACCEPTED"
        }
        print aud[ai, "audit_id"], aud[ai, "frame_id"], aud[ai, "craft_id"], aud[ai, "channel"], \
            cls, aud[ai, "payload_hash"], aud[ai, "verdict_code"], status >> (APP "/out/audit_report.csv")
    }
    print "matched_count=" mc > (APP "/out/audit_summary.txt")
    print "matched_frames=" ma >> (APP "/out/audit_summary.txt")
    print "rejected_count=" uc >> (APP "/out/audit_summary.txt")
    print "rejected_frames=" ua >> (APP "/out/audit_summary.txt")
}
AWKEOF

cat > "$T1/environment/src/audit_rules.pli" <<'EOF'
DCL ELIGIBLE_STATE CHAR(12) INIT('DOWNLINK');
DCL OPEN_PASS_STATE CHAR(8) INIT('ARMED');
DCL VERDICT_A CHAR(12) INIT('PASS');
DCL VERDICT_B CHAR(12) INIT('REVIEW');
DCL VERDICT_C CHAR(12) INIT('HOLD');
DCL ALIAS_1 CHAR(20) INIT('A=>ALPHA');
DCL ALIAS_2 CHAR(20) INIT('B=>BETA');
DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');
EOF

cat > "$T1/environment/src/audit_batch.pli" <<'EOF'
/* PL/I batch control deck for orbit downlink frame auditor. */
%SET KEY_COMPARE PREFIX5
%SET CONSUME OFF
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF

cat > "$T1/environment/data/catalog.psv" <<'EOF'
frame_id|craft_id|channel|payload_hash|recv_ts|state|service_class
FRM-10001|ALPHA|D1|8f2a11|20260612120000|DOWNLINK|TM
FRM-10002|BETA|D2|9b3c22|20260612120100|STALE|TM
EOF

cat > "$T1/environment/data/audits.psv" <<'EOF'
audit_id|frame_id|craft_id|channel|payload_hash|audit_ts|verdict_code|service_class
AUD-1|FRM-10001|ALPHA|D1|8f2a11|20260612120500|PASS|TM
EOF

cat > "$T1/environment/config/pass_windows.psv" <<'EOF'
craft_id|open_ts|close_ts|state
ALPHA|20260612115900|20260612123000|ARMED
EOF

cat > "$T1/environment/docs/operations.md" <<'EOF'
# Orbit Downlink Frame Auditor

The PL/I batch reconciles `/app/data/audits.psv` against `/app/data/catalog.psv`.
Policy constants live in `/app/src/audit_rules.pli`. Runtime switches are `%SET`
directives in `/app/src/audit_batch.pli`. Run `/app/scripts/run_batch.sh`.
Outputs: `/app/out/audit_report.csv`, `/app/out/audit_summary.txt`.
EOF

for n in 01 02 03; do
  echo "Support note $n for pass-window and alias normalization." > "$T1/environment/docs/audit_support_${n}.md"
done

echo "frame_id|craft_id|channel" > "$T1/environment/samples/example.psv"

# Instructions
cat > "$T1/steps/milestone_1/instruction.md" <<'EOF'
The orbit downlink frame PL/I auditor rejects valid catalog matches. Fix `/app/src/audit_batch.pli`, `/app/src/audit_rules.pli`, or the batch harness so `/app/data/audits.psv` reconciles against `/app/data/catalog.psv`.

Milestone 1 requires full-key agreement on `frame_id`, `craft_id`, `channel`, `payload_hash`, and `service_class`, catalog `state` equal to `ELIGIBLE_STATE` from `/app/src/audit_rules.pli`, and `verdict_code` one of `VERDICT_A`, `VERDICT_B`, or `VERDICT_C`. Each catalog row may be consumed once. Preserve audit order. Write `/app/out/audit_report.csv` with documented columns, blank `service_class` for rejected rows, and `/app/out/audit_summary.txt` counters.

Status must be exactly `ACCEPTED` or `REJECTED`.
EOF

cat > "$T1/steps/milestone_2/instruction.md" <<'EOF'
The orbit downlink frame PL/I auditor rejects valid catalog matches. Fix `/app/src/audit_batch.pli`, `/app/src/audit_rules.pli`, or the batch harness so `/app/data/audits.psv` reconciles against `/app/data/catalog.psv`.

Milestone 2 keeps milestone 1 rules and enables `ALIAS_*` normalization from `/app/src/audit_rules.pli` (`raw=>canonical`, case-insensitive). Emit canonical `service_class` for accepted rows.

Status must be exactly `ACCEPTED` or `REJECTED`.
EOF

cat > "$T1/steps/milestone_3/instruction.md" <<'EOF'
The orbit downlink frame PL/I auditor rejects valid catalog matches. Fix `/app/src/audit_batch.pli`, `/app/src/audit_rules.pli`, or the batch harness so `/app/data/audits.psv` reconciles against `/app/data/catalog.psv`.

Milestone 3 keeps prior rules and adds `/app/config/pass_windows.psv`. Timestamps are 14-digit UTC strings. Catalog `recv_ts` and audit `audit_ts` must fall inside an open pass window for the craft using `OPEN_PASS_STATE`. Multiple unused candidates pick latest `recv_ts` then earliest catalog row.

Status must be exactly `ACCEPTED` or `REJECTED`.
EOF

# Tests - task 1
cat > "$T1/steps/milestone_1/tests/test_m1.py" <<'PYEOF'
"""Verifier tests for orbit downlink frame PL/I auditor."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CAT = APP / "data/catalog.psv"
AUD = APP / "data/audits.psv"
WIN = APP / "config/pass_windows.psv"
RULES = APP / "src/audit_rules.pli"
BATCH = APP / "src/audit_batch.pli"
REPORT = APP / "out/audit_report.csv"
SUMMARY = APP / "out/audit_summary.txt"


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(r) for r in rows) + "\n")


def write_rules(status="DOWNLINK", open_state="ARMED", verdicts=("PASS", "REVIEW", "HOLD"), aliases=("A=>ALPHA", "B=>BETA", "X=>XLINK")):
    lines = [
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{status}');",
        f"DCL OPEN_PASS_STATE CHAR(8) INIT('{open_state}');",
        f"DCL VERDICT_A CHAR(12) INIT('{verdicts[0]}');",
        f"DCL VERDICT_B CHAR(12) INIT('{verdicts[1]}');",
        f"DCL VERDICT_C CHAR(12) INIT('{verdicts[2]}');",
    ]
    lines += [f"DCL ALIAS_{i + 1} CHAR(20) INIT('{a}');" for i, a in enumerate(aliases)]
    RULES.write_text("\n".join(lines) + "\n")


def write_inputs(cat, aud, wins):
    write_psv(CAT, ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"], cat)
    write_psv(AUD, ["audit_id", "frame_id", "craft_id", "channel", "payload_hash", "audit_ts", "verdict_code", "service_class"], aud)
    write_psv(WIN, ["craft_id", "open_ts", "close_ts", "state"], wins)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        k, v = line.split("=", 1)
        summary[k] = int(v)
    return rows, summary


def test_milestone1_full_gates_consumption_and_totals():
    write_rules(status="ARMED", verdicts=("OK", "WATCH", "DONE"))
    write_inputs(
        [
            ["FRM-1", "ALPHA", "D1", "aa", "20260612120000", "ARMED", "TM"],
            ["FRM-2", "BETA", "D2", "bb", "20260612120100", "BAD", "TM"],
            ["FRM-3", "ALPHA", "D3", "cc", "20260612120200", "ARMED", "TM"],
        ],
        [
            ["AUD-1", "FRM-1", "ALPHA", "D1", "aa", "20260612120500", "OK", "TM"],
            ["AUD-2", "FRM-1", "ALPHA", "D1", "aa", "20260612120600", "OK", "TM"],
            ["AUD-3", "FRM-2", "BETA", "D2", "bb", "20260612120700", "OK", "TM"],
            ["AUD-4", "FRM-3", "WRONG", "D3", "cc", "20260612120700", "WATCH", "TM"],
            ["AUD-5", "FRM-3", "ALPHA", "D3", "dd", "20260612120700", "WATCH", "TM"],
            ["AUD-6", "FRM-3", "ALPHA", "D3", "cc", "20260612120700", "NOPE", "TM"],
        ],
        [["ALPHA", "20260612115900", "20260612123000", "ARMED"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["ACCEPTED", "REJECTED", "REJECTED", "REJECTED", "REJECTED", "REJECTED"]
    assert rows[1]["service_class"] == ""
    assert summary == {"matched_count": 1, "matched_frames": 1, "rejected_count": 5, "rejected_frames": 5}
PYEOF

cat > "$T1/steps/milestone_2/tests/test_m2.py" <<'PYEOF'
"""Verifier tests for orbit downlink frame PL/I auditor milestone 2."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CAT = APP / "data/catalog.psv"
AUD = APP / "data/audits.psv"
WIN = APP / "config/pass_windows.psv"
RULES = APP / "src/audit_rules.pli"
REPORT = APP / "out/audit_report.csv"
SUMMARY = APP / "out/audit_summary.txt"


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(r) for r in rows) + "\n")


def write_rules(**kwargs):
    status = kwargs.get("status", "DOWNLINK")
    open_state = kwargs.get("open_state", "ARMED")
    verdicts = kwargs.get("verdicts", ("PASS", "REVIEW", "HOLD"))
    aliases = kwargs.get("aliases", ("A=>ALPHA", "B=>BETA", "X=>XLINK"))
    lines = [
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{status}');",
        f"DCL OPEN_PASS_STATE CHAR(8) INIT('{open_state}');",
        f"DCL VERDICT_A CHAR(12) INIT('{verdicts[0]}');",
        f"DCL VERDICT_B CHAR(12) INIT('{verdicts[1]}');",
        f"DCL VERDICT_C CHAR(12) INIT('{verdicts[2]}');",
    ]
    lines += [f"DCL ALIAS_{i + 1} CHAR(20) INIT('{a}');" for i, a in enumerate(aliases)]
    RULES.write_text("\n".join(lines) + "\n")


def write_inputs(cat, aud, wins):
    write_psv(CAT, ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"], cat)
    write_psv(AUD, ["audit_id", "frame_id", "craft_id", "channel", "payload_hash", "audit_ts", "verdict_code", "service_class"], aud)
    write_psv(WIN, ["craft_id", "open_ts", "close_ts", "state"], wins)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {k: int(v) for k, v in (line.split("=", 1) for line in SUMMARY.read_text().splitlines())}
    return rows, summary


def test_milestone2_alias_normalization():
    write_rules(status="LIVE", verdicts=("GO", "CHK", "WAIT"), aliases=("a=>ALPHA", "tm=>TM", "x=>XLINK"))
    write_inputs(
        [["FRM-9", "a", "D1", "ff", "20260612120000", "LIVE", "tm"]],
        [["AUD-9", "FRM-9", "A", "D1", "ff", "20260612120500", "go", "TM"]],
        [["ALPHA", "20260612115900", "20260612123000", "ARMED"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "ACCEPTED"
    assert rows[0]["service_class"] == "TM"
    assert summary["matched_count"] == 1
PYEOF

cat > "$T1/steps/milestone_3/tests/test_m3.py" <<'PYEOF'
"""Verifier tests for orbit downlink frame PL/I auditor milestone 3."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CAT = APP / "data/catalog.psv"
AUD = APP / "data/audits.psv"
WIN = APP / "config/pass_windows.psv"
RULES = APP / "src/audit_rules.pli"
REPORT = APP / "out/audit_report.csv"
SUMMARY = APP / "out/audit_summary.txt"


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(r) for r in rows) + "\n")


def write_rules(status="DOWNLINK", open_state="ARMED", verdicts=("PASS", "REVIEW", "HOLD"), aliases=("A=>ALPHA", "B=>BETA", "X=>XLINK")):
    lines = [
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{status}');",
        f"DCL OPEN_PASS_STATE CHAR(8) INIT('{open_state}');",
        f"DCL VERDICT_A CHAR(12) INIT('{verdicts[0]}');",
        f"DCL VERDICT_B CHAR(12) INIT('{verdicts[1]}');",
        f"DCL VERDICT_C CHAR(12) INIT('{verdicts[2]}');",
    ]
    lines += [f"DCL ALIAS_{i + 1} CHAR(20) INIT('{a}');" for i, a in enumerate(aliases)]
    RULES.write_text("\n".join(lines) + "\n")


def write_inputs(cat, aud, wins):
    write_psv(CAT, ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"], cat)
    write_psv(AUD, ["audit_id", "frame_id", "craft_id", "channel", "payload_hash", "audit_ts", "verdict_code", "service_class"], aud)
    write_psv(WIN, ["craft_id", "open_ts", "close_ts", "state"], wins)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {k: int(v) for k, v in (line.split("=", 1) for line in SUMMARY.read_text().splitlines())}
    return rows, summary


def test_milestone3_window_and_candidate_tiebreak():
    write_rules(status="OPEN", open_state="OPEN", verdicts=("OK", "WATCH", "DONE"))
    write_inputs(
        [
            ["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"],
            ["FRM-A", "ALPHA", "D1", "h1", "20260612120100", "OPEN", "TM"],
        ],
        [["AUD-W", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"]],
        [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "ACCEPTED"
    assert summary["matched_count"] == 1

    write_inputs(
        [
            ["FRM-B", "ALPHA", "D1", "h2", "20260612120000", "OPEN", "TM"],
            ["FRM-B", "ALPHA", "D1", "h2", "20260612120100", "OPEN", "TM"],
        ],
        [["AUD-X", "FRM-B", "ALPHA", "D1", "h2", "20260612130000", "OK", "TM"]],
        [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "REJECTED"
PYEOF

for m in 1 2 3; do
  write_test_sh "$m" "test_m${m}.py" "$T1"
done

patch_batch() {
  local file="$1"
  shift
  local content='/* PL/I batch control deck for orbit downlink frame auditor. */'
  for kv in "$@"; do
    content+=$'\n%SET '"$kv"
  done
  printf '%s\n' "$content" > "$file"
}

SOLVE1='cat > /app/src/audit_batch.pli <<'"'"'EOF'"'"'
/* PL/I batch control deck for orbit downlink frame auditor. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
EOF'

SOLVE2='cat > /app/src/audit_batch.pli <<'"'"'EOF'"'"'
/* PL/I batch control deck for orbit downlink frame auditor. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
EOF'

SOLVE3='cat > /app/src/audit_batch.pli <<'"'"'EOF'"'"'
/* PL/I batch control deck for orbit downlink frame auditor. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
EOF'

write_solve_chain "$T1" 1 "$SOLVE1"
write_solve_chain "$T1" 2 "$SOLVE2"
write_solve_chain "$T1" 3 "$SOLVE3"

echo "Created $T1"
