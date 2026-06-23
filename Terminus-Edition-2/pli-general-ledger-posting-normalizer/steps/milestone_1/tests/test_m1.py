import csv
import subprocess
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
    rows=list(csv.DictReader((APP/"out/posting_report.csv").open(), delimiter="|"))
    summary={k:int(v) for k,v in (line.split("=", 1) for line in (APP/"out/posting_summary.txt").read_text().splitlines())}
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
    assert summary=={"posted_count":2,"posted_amount_cents":40,"rejected_count":4,"rejected_amount_cents":91}
