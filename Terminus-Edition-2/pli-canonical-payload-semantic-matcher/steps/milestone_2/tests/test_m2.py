import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out"/"semantic_report.csv").open(), delimiter="|"))
def test_m2():
    rules_path = list((APP/"src").glob("*_rules.pli"))[0]
    rules_path.write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\nDCL OPEN_COMPARE_STATE CHAR(8) INIT('OPEN');\nDCL REASON_1 CHAR(12) INIT('GO');\nDCL REASON_2 CHAR(12) INIT('CHK');\nDCL REASON_3 CHAR(12) INIT('WAIT');\nDCL ALIAS_1 CHAR(20) INIT('f=>FED');\nDCL ALIAS_2 CHAR(20) INIT('a=>ACH');\nDCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');\n")
    if "segment_id" == "tolerance_key":
        m2_src=["R-9","991100","99","f","NYC","20260612120000","LIVE","tm"]
        m2_act=["C9","R-9","991100","99","FED","20260612120500","go","NYC"]
    else:
        m2_src=["R-9","991100","99","FED","f","20260612120000","LIVE","tm"]
        m2_act=["C9","R-9","991100","99","FED","20260612120500","go","FED"]
    w(APP/"data"/"expected.psv",["field_id","schema_id","payload_hash","tolerance_key","segment_id","recv_ts","state","kind_code"],[m2_src])
    w(APP/"data"/"actual.psv",["claim_id","field_id","schema_id","payload_hash","tolerance_key","check_ts","mode_code","segment_id"],[m2_act])
    w(APP/"config"/"compare_windows.psv",["schema_id","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="EQUAL" and rows[0]["segment_id"]=="FED"
