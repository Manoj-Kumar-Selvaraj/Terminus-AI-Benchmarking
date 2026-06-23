#!/usr/bin/env bash
set -euxo pipefail
bash /steps/milestone_1/solution/solve1.sh
mkdir -p /tmp/outtest /tmp/work
cp /app/data/master_seed.json /tmp/work/db.json
cat > /tmp/work/in.fb <<'EOF'
HT1MISS100 20260618VERIFY  
D000001AC1000000001BAL+000000001250GRP001M1A00001
D000002ACMISSING001BAL+000000000999GRP001M1A00002
D000003AC1000000002RAT+000000000425GRP002M1A00003
TT1MISS100 000003+000000001250
EOF
/app/bin/run_finbulk.sh --batch T1MISS100 --input /tmp/work/in.fb --db /tmp/work/db.json --out /tmp/outtest
echo "exit=$?"
ls -la /tmp/outtest/
cat /tmp/outtest/summary_T1MISS100.json 2>/dev/null || echo "no summary"
cat /tmp/finbulk_bridge.out 2>/dev/null || echo "no bridge out"
