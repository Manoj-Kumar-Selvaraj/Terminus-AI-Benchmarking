import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out"/"trailer_report.csv").open(), delimiter="|"))
def test_m3():
    rules_path = list((APP/"src").glob("*_rules.pli"))[0]
    rules_path.write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\nDCL OPEN_SETTLE_STATE CHAR(8) INIT('OPEN');\nDCL REASON_1 CHAR(12) INIT('OK');\nDCL REASON_2 CHAR(12) INIT('WATCH');\nDCL REASON_3 CHAR(12) INIT('DONE');\nDCL ALIAS_1 CHAR(20) INIT('D=>DEBIT');\nDCL ALIAS_2 CHAR(20) INIT('A=>ACH');\nDCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');\n")
    w(APP/"data"/"batches.psv",["batch_id","account_no","net_cents","dc_flag","branch_id","posted_ts","state","kind_code"],[
        ["R-A","991100","10","FED","NYC","20260612120000","OPEN","TM"],
        ["R-A","991100","10","FED","NYC","20260612120100","OPEN","TM"],
    ])
    w(APP/"data"/"trailer_claims.psv",["claim_id","batch_id","account_no","net_cents","dc_flag","claim_ts","reason_code","branch_id"],[["C-W","R-A","991100","10","FED","20260612120500","OK","NYC"]])
    w(APP/"config"/"settlement_windows.psv",["account_no","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    assert run()[0]["status"]=="BALANCED"
    w(APP/"data"/"trailer_claims.psv",["claim_id","batch_id","account_no","net_cents","dc_flag","claim_ts","reason_code","branch_id"],[["C-X","R-A","991100","10","FED","20260612130000","OK","NYC"]])
    assert run()[0]["status"]=="REJECTED"
