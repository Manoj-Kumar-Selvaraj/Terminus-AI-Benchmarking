import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    return list(csv.DictReader((APP/"out/fragment_report.csv").open(), delimiter="|"))
def test_m3():
    (APP/"src/fragment_rules.pli").write_text("DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\nDCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');\nDCL OPCODE_1 CHAR(12) INIT('OK');\nDCL OPCODE_2 CHAR(12) INIT('WATCH');\nDCL OPCODE_3 CHAR(12) INIT('DONE');\nDCL ALIAS_1 CHAR(20) INIT('N=>NORTH');\nDCL ALIAS_2 CHAR(20) INIT('S=>SOUTH');\nDCL ALIAS_3 CHAR(20) INIT('E=>EDGE');\n")
    w(APP/"data/fragments.psv",["fragment_id","parent_id","shard_value","channel","ingest_ts","state","ingest_class"],[
        ["FRG-A","P-A","5","NORTH","20260612120000","OPEN","LEDGER"],
        ["FRG-A","P-A","5","NORTH","20260612120100","OPEN","LEDGER"],
    ])
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[["M-W","FRG-A","P-A","5","NORTH","20260612120500","OK","LEDGER"]])
    w(APP/"config/shard_windows.psv",["channel","open_ts","close_ts","state"],[["NORTH","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    assert run()[0]["status"]=="LINKED"
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[["M-X","FRG-A","P-A","5","NORTH","20260612130000","OK","LEDGER"]])
    assert run()[0]["status"]=="ORPHAN"
