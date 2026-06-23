#!/usr/bin/env bash
set -Eeuo pipefail
cat > /app/src/payroll_runtime.py <<'PYRT'
#!/usr/bin/env python3
import csv, os, sys
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

FEATURE_LEVEL = 2
APP = Path('/app')
DATA = APP/'data'; CFG = APP/'config'; OUT = APP/'out'

def read_psv(path):
    if not path.exists(): return []
    with path.open(newline='') as h: return list(csv.DictReader(h, delimiter='|'))

def write_psv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as h:
        w = csv.writer(h, delimiter='|', lineterminator='\n')
        w.writerow(header); w.writerows(rows)

def dec(v): return Decimal(str(v or '0'))
def cents(v): return int(dec(v).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def period_in_range(period, start, end): return start <= period <= end

def parse_tax():
    rules = read_psv(CFG/'tax_rules.psv')
    return sorted([(dec(r['from_cents']), dec(r['to_cents']), dec(r['rate_bp'])) for r in rules], key=lambda x:x[0])

def tax_on(amount, rules):
    amt = dec(amount); total = Decimal(0)
    for lo, hi, bp in rules:
        if amt > lo:
            taxable = min(amt, hi) - lo
            if taxable > 0: total += taxable * bp / Decimal(10000)
    return cents(total)

def active_comp(employee_id, period, history):
    rows = [r for r in history if r['employee_id']==employee_id and period >= r['effective_from']]
    if not rows: return None
    if FEATURE_LEVEL == 0:
        return sorted(rows, key=lambda r: r['effective_from'])[-1]  # wrongly newest overall for every period
    return sorted(rows, key=lambda r: r['effective_from'])[-1]

def corrected_for_period(emp, period, prior, comp):
    base = dec(comp['base_cents'])
    allowance = dec(comp.get('allowance_cents','0'))
    overtime_hours = dec(prior.get('overtime_hours','0'))
    overtime_rate_bp = dec(comp.get('overtime_rate_bp','0'))
    # M2: ordered stages: base -> allowance -> overtime from base hourly proxy only.
    if FEATURE_LEVEL < 2:
        gross = (base + allowance) * (Decimal(1) + (overtime_hours * overtime_rate_bp / Decimal(10000)))
    else:
        overtime = (base * overtime_hours * overtime_rate_bp / Decimal(10000))
        gross = base + allowance + overtime
    return cents(gross)

def load_prior_ledgers():
    prior_pay = {(r['employee_id'], r['period']): r for r in read_psv(DATA/'prior_payroll.psv')}
    prior_adj = {r['adjustment_id']: r for r in read_psv(DATA/'prior_adjustment_ledger.psv')}
    return prior_pay, prior_adj

def employee_order(rows):
    seen=[]
    for r in rows:
        if r['employee_id'] not in seen: seen.append(r['employee_id'])
    return seen

def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob('*'):
        if FEATURE_LEVEL < 4 or p.name not in ('adjustment_ledger.psv','restart_checkpoint.txt'):
            p.unlink()
    employees = read_psv(DATA/'employees.psv')
    history = read_psv(DATA/'compensation_history.psv')
    prior_pay, prior_adj = load_prior_ledgers()
    tax_rules = parse_tax()
    deduct = {r['employee_id']: dec(r['cap_cents']) for r in read_psv(CFG/'deduction_caps.psv')}
    periods_by_emp={}
    for (emp, per), p in prior_pay.items(): periods_by_emp.setdefault(emp, []).append(per)
    ledger_rows=[]; report_rows=[]; tax_rows=[]; reject_rows=[]
    existing_ids=set()
    if FEATURE_LEVEL >= 4 and (OUT/'adjustment_ledger.psv').exists():
        old=read_psv(OUT/'adjustment_ledger.psv')
        ledger_rows=[[r['adjustment_id'],r['employee_id'],r['period'],r['gross_delta_cents'],r['tax_delta_cents'],r['deduction_delta_cents'],r['net_delta_cents'],r['status']] for r in old]
        existing_ids={r[0] for r in ledger_rows}
    abend_after = int(os.environ.get('ABEND_AFTER_EMPLOYEES','0') or '0')
    processed=0
    emp_ids = [e['employee_id'] for e in employees]
    for emp in emp_ids:
        # restart skips employees fully checkpointed
        if FEATURE_LEVEL >= 4 and (OUT/'restart_checkpoint.txt').exists():
            ck=(OUT/'restart_checkpoint.txt').read_text().strip().split('|')[-1]
            if ck and emp <= ck:
                continue
        emp_periods=sorted(periods_by_emp.get(emp, []))
        emp_new_rows=[]
        for per in emp_periods:
            prior=prior_pay[(emp,per)]
            comp=active_comp(emp, per, history)
            if not comp:
                reject_rows.append([emp, per, 'COMPENSATION_RULE_MISSING']); continue
            corrected=corrected_for_period(emp, per, prior, comp)
            gross_delta=corrected - int(prior['gross_cents'])
            if gross_delta == 0: continue
            # M3: tax/deduction calculated on retro delta; older logic recalculates total and subtracts loosely.
            if FEATURE_LEVEL < 3:
                tax_delta = tax_on(corrected, tax_rules) - tax_on(int(prior['gross_cents']), tax_rules)
                deduction_delta = min(cents(dec(corrected)*Decimal('0.05')), int(deduct.get(emp, Decimal(999999999)))) - int(prior.get('deduction_cents','0'))
            else:
                tax_delta = tax_on(max(gross_delta,0), tax_rules) if gross_delta>0 else -tax_on(abs(gross_delta), tax_rules)
                remaining_cap = max(int(deduct.get(emp, Decimal(999999999))) - int(prior.get('deduction_cents','0')), 0)
                deduction_delta = min(cents(max(Decimal(gross_delta),Decimal(0))*Decimal('0.05')), remaining_cap)
            net_delta = gross_delta - tax_delta - deduction_delta
            adj_id=f'ADJ-{emp}-{per}'
            if adj_id in prior_adj or adj_id in existing_ids: continue
            emp_new_rows.append([adj_id, emp, per, str(gross_delta), str(tax_delta), str(deduction_delta), str(net_delta), 'COMMITTED'])
            report_rows.append([emp, per, str(int(prior['gross_cents'])), str(corrected), str(gross_delta), 'ADJUSTMENT_POSTED'])
            tax_rows.append([emp, per, str(gross_delta), str(tax_delta), str(deduction_delta), str(net_delta)])
        ledger_rows.extend(emp_new_rows); existing_ids.update(r[0] for r in emp_new_rows)
        processed += 1
        if FEATURE_LEVEL >= 4:
            write_psv(OUT/'adjustment_ledger.psv', ['adjustment_id','employee_id','period','gross_delta_cents','tax_delta_cents','deduction_delta_cents','net_delta_cents','status'], ledger_rows)
            (OUT/'restart_checkpoint.txt').write_text('LAST_COMMITTED_EMPLOYEE|'+emp+'\n')
        if abend_after and processed >= abend_after:
            print('ABEND: simulated payroll posting interruption after employee '+emp, file=sys.stderr)
            sys.exit(17)
    if FEATURE_LEVEL < 4:
        write_psv(OUT/'adjustment_ledger.psv', ['adjustment_id','employee_id','period','gross_delta_cents','tax_delta_cents','deduction_delta_cents','net_delta_cents','status'], ledger_rows)
    write_psv(OUT/'period_delta_report.psv', ['employee_id','period','prior_gross_cents','corrected_gross_cents','gross_delta_cents','decision'], report_rows)
    write_psv(OUT/'tax_delta_report.psv', ['employee_id','period','gross_delta_cents','tax_delta_cents','deduction_delta_cents','net_delta_cents'], tax_rows)
    write_psv(OUT/'reject_ledger.psv', ['employee_id','period','reason_code'], reject_rows)
    total_gross=sum(int(r[3]) for r in ledger_rows); total_tax=sum(int(r[4]) for r in ledger_rows); total_net=sum(int(r[6]) for r in ledger_rows)
    write_psv(OUT/'control_totals.psv', ['metric','value'], [['adjustment_count',str(len(ledger_rows))],['gross_delta_cents',str(total_gross)],['tax_delta_cents',str(total_tax)],['net_delta_cents',str(total_net)]])
if __name__ == '__main__': main()
PYRT
chmod +x /app/src/payroll_runtime.py
