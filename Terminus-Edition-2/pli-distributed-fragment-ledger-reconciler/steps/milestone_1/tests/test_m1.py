import csv
import subprocess
from pathlib import Path
APP=Path("/app")
def w(p,h,r): p.write_text("|".join(h)+"\n"+"\n".join("|".join(x) for x in r)+"\n")
def rules(st="ACTIVE",ops=("APPEND","RELINK","CLOSE")):
    (APP/"src/fragment_rules.pli").write_text("\n".join([
        f"DCL ELIGIBLE_STATE CHAR(12) INIT('{st}');","DCL OPEN_SHARD_STATE CHAR(8) INIT('OPEN');",
        f"DCL OPCODE_1 CHAR(12) INIT('{ops[0]}');",f"DCL OPCODE_2 CHAR(12) INIT('{ops[1]}');",f"DCL OPCODE_3 CHAR(12) INIT('{ops[2]}');",
        "DCL ALIAS_1 CHAR(20) INIT('N=>NORTH');","DCL ALIAS_2 CHAR(20) INIT('S=>SOUTH');","DCL ALIAS_3 CHAR(20) INIT('E=>EDGE');"])+"\n")
def run():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    rows=list(csv.DictReader((APP/"out/fragment_report.csv").open(), delimiter="|"))
    summary={k:int(v) for k,v in (line.split("=", 1) for line in (APP/"out/fragment_summary.txt").read_text().splitlines())}
    return rows,summary
def test_m1():
    rules(st="LIVE",ops=("OK","WATCH","DONE"))
    w(APP/"data/fragments.psv",["fragment_id","parent_id","shard_value","channel","ingest_ts","state","ingest_class"],[
        ["FRG-1","P-1","10","NORTH","20260612120000","LIVE","LEDGER"],
        ["FRG-2","P-2","20","SOUTH","20260612120100","BAD","LEDGER"],
        ["FRG-3","P-3","30","EDGE","20260612120200","LIVE","LEDGER"],
    ])
    w(APP/"data/merges.psv",["merge_id","fragment_id","parent_id","shard_value","channel","merge_ts","opcode","ingest_class"],[
        ["M1","FRG-1","P-1","10","NORTH","20260612120500","OK","LEDGER"],
        ["M2","FRG-1","P-1","10","NORTH","20260612120600","OK","LEDGER"],
        ["M3","FRG-2","P-2","20","SOUTH","20260612120700","OK","LEDGER"],
        ["M4","FRG-3","BAD","30","EDGE","20260612120700","WATCH","LEDGER"],
        ["M5","FRG-3","P-3","31","EDGE","20260612120700","WATCH","LEDGER"],
        ["M6","FRG-3","P-3","30","EDGE","20260612120700","NOPE","LEDGER"],
    ])
    w(APP/"config/shard_windows.psv",["channel","open_ts","close_ts","state"],[["NORTH","20260612115900","20260612123000","OPEN"]])
    (APP/"out").mkdir(exist_ok=True)
    rows,summary=run()
    assert [r["status"] for r in rows]==["LINKED","ORPHAN","ORPHAN","ORPHAN","ORPHAN","ORPHAN"]
    assert rows[1]["ingest_class"]==""
    assert summary=={"linked_count":1,"linked_shards":10,"orphan_count":5,"orphan_shards":121}
