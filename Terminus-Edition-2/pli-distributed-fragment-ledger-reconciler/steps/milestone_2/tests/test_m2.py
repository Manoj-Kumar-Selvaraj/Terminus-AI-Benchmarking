import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/fragment_report.csv").open(), delimiter="|"))
def test_m2():
    (APP/"src/fragment_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\nDCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');\nDCL OPCODE_1 CHAR(12) INIT('GO');\nDCL OPCODE_2 CHAR(12) INIT('CHK');\nDCL OPCODE_3 CHAR(12) INIT('WAIT');\nDCL ALIAS_1 CHAR(20) INIT('n=>NORTH');\nDCL ALIAS_2 CHAR(20) INIT('lg=>LEDGER');\nDCL ALIAS_3 CHAR(20) INIT('e=>EDGE');\n")
    w(APP/"data/fragments.psv",["fragment_id","parent_id","shard_value","channel","ingest_ts","state","ingest_class"],[["FRG-9","P-9","7","n","20260612120000","LIVE","lg"]])
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[["M9","FRG-9","P-9","7","NORTH","20260612120500","go","LEDGER"]])
    w(APP/"config/shard_windows.psv",["channel","open_ts","close_ts","state"],[["NORTH","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows=run()
    assert rows[0]["status"]=="LINKED" and rows[0]["ingest_class"]=="LEDGER"
