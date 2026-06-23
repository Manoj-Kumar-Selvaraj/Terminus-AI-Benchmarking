#!/bin/bash
set -euo pipefail
cat > /app/scripts/run_pl1.py <<'PY'
#!/usr/bin/env python3
import csv,re
from pathlib import Path
APP=Path('/app')

def norm(x): return (x or '').strip().upper()
def read_psv(path):
    with path.open(newline='') as f: return [{k:(v or '').strip() for k,v in r.items()} for r in csv.DictReader(f, delimiter='|')]
def read_rules():
    vals={}; aliases={}
    for line in (APP/'src/reconcile_rules.pli').read_text().splitlines():
        raw=line.strip()
        upper=raw.upper()
        if not upper.startswith('DCL ') or ' INIT(' not in upper:
            continue
        name=raw.split()[1].upper()
        marker="INIT('"
        if marker in raw and "')" in raw:
            val=raw.split(marker,1)[1].split("')",1)[0].strip()
            vals[name]=val
    for k,v in vals.items():
        if k.startswith('ALIAS_') and '=>' in v:
            a,b=v.split('=>',1); aliases[norm(a)]=norm(b); aliases[norm(b)]=norm(b)
    return vals, aliases
def canon(x,aliases): return aliases.get(norm(x), norm(x))
def nts(x): return len(x)==14 and x.isdigit()
def win_ok(s,a,wins,open_state):
    st=s['admit_ts']; at=a['transfer_ts']
    if not nts(st) or not nts(at): return False
    for w in wins:
        if w['ward_id'] == s['ward_id'] and norm(w['state']) == norm(open_state):
            o=w['open_ts']; c=w['close_ts']
            if nts(o) and nts(c) and o <= st <= c and st <= at <= c: return True
    return False
def main():
    vals,aliases=read_rules(); eligible=norm(vals['ELIGIBLE_STATUS']); open_state=vals['OPEN_WINDOW_STATUS']
    reasons={norm(vals['REASON_A']), norm(vals['REASON_B']), norm(vals['REASON_C'])}
    src=read_psv(APP/'data/beds.psv'); acts=read_psv(APP/'data/transfers.psv'); wins=read_psv(APP/'config/windows.psv')
    for s in src: s['_used']=False; s['_canon']=canon(s['bed_type'], aliases)
    rows=[]; mc=uc=ma=ua=0
    for a in acts:
        ac=canon(a['bed_type'], aliases); best=None
        for i,s in enumerate(src):
            if s['_used']: continue
            if not (s['bed_id']==a['bed_id'] and s['patient_id']==a['patient_id'] and s['ward_id']==a['ward_id'] and s['nurse_unit']==a['nurse_unit'] and s['charge_cents']==a['charge_cents']): continue
            if norm(s['status']) != eligible or norm(a['reason']) not in reasons: continue
            if s['_canon'] != ac: continue
            if not win_ok(s,a,wins,open_state): continue
            if best is None or s['admit_ts'] > src[best]['admit_ts']: best=i
        amt=int(a['charge_cents'])
        if best is None:
            uc+=1; ua+=amt; kind=''; status='UNMATCHED'
        else:
            src[best]['_used']=True; mc+=1; ma+=amt; kind=src[best]['_canon']; status='MATCHED'
        rows.append([a['action_id'],a['bed_id'],a['patient_id'],a['ward_id'],kind,a['charge_cents'],a['reason'],status])
    (APP/'out').mkdir(exist_ok=True)
    with (APP/'out/transfer_report.csv').open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['action_id','bed_id','patient_id','ward_id','bed_type','charge_cents','reason','status']); w.writerows(rows)
    (APP/'out/transfer_summary.txt').write_text(f'matched_count={mc}\nmatched_amount_cents={ma}\nunmatched_count={uc}\nunmatched_amount_cents={ua}\n')
if __name__=='__main__': main()
PY
chmod +x /app/scripts/run_pl1.py
/app/scripts/run_batch.sh
