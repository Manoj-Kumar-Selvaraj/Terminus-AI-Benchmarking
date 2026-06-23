import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/posting_report.csv").open(), delimiter="|"))
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
