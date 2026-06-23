import csv
import subprocess
from pathlib import Path
APP = Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def rules(st="POSTED",rs=("MATCH","CHK","DONE")):
    rules_path = list((APP/"src").glob("*_rules.pli"))[0]
    rules_path.write_text("\n".join([
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{st}');", "DCL OPEN_COMPARE_STATE CHAR(8) INIT('OPEN');",
        f"DCL REASON_1 CHAR(12) INIT('{rs[0]}');", "DCL REASON_2 CHAR(12) INIT('WATCH');", "DCL REASON_3 CHAR(12) INIT('DONE');",
        "DCL ALIAS_1 CHAR(20) INIT('S=>STRING');", "DCL ALIAS_2 CHAR(20) INIT('B=>BETA');", "DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');"])+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = APP/"out"/"semantic_report.csv"
    rows=list(csv.DictReader(report.open(), delimiter="|"))
    summary={k:int(v) for k,v in (line.split("=", 1) for line in (APP/"out"/"semantic_summary.txt").read_text().splitlines())}
    return rows,summary
def test_m1():
    rules(st="LIVE",rs=("OK","WATCH","DONE"))
    w(APP/"data"/"expected.psv",["field_id","schema_id","payload_hash","tolerance_key","segment_id","recv_ts","state","kind_code"],[
        ["R-1","991100","10","FED","NYC","20260612120000","LIVE","TM"],
        ["R-2","991200","20","ACH","NYC","20260612120100","BAD","TM"],
        ["R-3","991300","30","SWIFT","BOS","20260612120200","LIVE","TM"],
    ])
    w(APP/"data"/"actual.psv",["claim_id","field_id","schema_id","payload_hash","tolerance_key","check_ts","mode_code","segment_id"],[
        ["C1","R-1","991100","10","FED","20260612120500","OK","NYC"],
        ["C2","R-1","991100","10","FED","20260612120600","OK","NYC"],
        ["C3","R-2","991200","20","ACH","20260612120700","OK","NYC"],
        ["C4","R-3","991300","30","SWIFT","20260612120700","WATCH","BOS"],
        ["C5","R-3","991300","31","SWIFT","20260612120700","WATCH","BOS"],
        ["C6","R-3","991300","30","SWIFT","20260612120700","NOPE","BOS"],
    ])
    w(APP/"config"/"compare_windows.psv",["schema_id","open_ts","close_ts","state"],[["991100","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows,summary=run()
    assert [r["status"] for r in rows]==["EQUAL","DIFFER","DIFFER","EQUAL","DIFFER","DIFFER"]
    assert rows[1]["segment_id"]==""
    assert summary=={"equal_count":2,"equal_fields":40,"differ_count":4,"differ_fields":91}
