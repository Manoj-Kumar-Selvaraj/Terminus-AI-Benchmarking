import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/posting_report.csv").open(), delimiter="|"))
def test_m2():
    (APP/"src/posting_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\nDCL OPEN_BOOK_STATE CHAR(8) INIT('OPEN');\nDCL ENTRY_1 CHAR(12) INIT('GO');\nDCL ENTRY_2 CHAR(12) INIT('CHK');\nDCL ENTRY_3 CHAR(12) INIT('WAIT');\nDCL ALIAS_1 CHAR(20) INIT('gl=>GENERAL');\nDCL ALIAS_2 CHAR(20) INIT('ap=>PAYABLE');\nDCL ALIAS_3 CHAR(20) INIT('ar=>RECEIVABLE');\n")
    w(APP/"data/journal.psv",["posting_id","account","amount_cents","ctrl_hash","book_ts","state","ledger_class"],[["PST-9","400100","99","ff","20260612120000","LIVE","gl"]])
    w(APP/"data/postings.psv",["entry_id","posting_id","account","amount_cents","ctrl_hash","post_ts","entry_type","ledger_class"],[["E9","PST-9","400100","99","ff","20260612120500","go","GENERAL"]])
    w(APP/"config/book_windows.psv",["account","open_ts","close_ts","state"],[["400100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="POSTED" and rows[0]["ledger_class"]=="GENERAL"
