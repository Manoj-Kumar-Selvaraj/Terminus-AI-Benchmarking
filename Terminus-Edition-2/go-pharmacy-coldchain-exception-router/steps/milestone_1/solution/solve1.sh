#!/usr/bin/env bash
set -euo pipefail

cd /app

if grep -q 'package_typeOK(s string) bool{return s=="CHEM"||s=="HEME"}' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/coldchain_exception_report.csv
  test -s /app/out/coldchain_exception_summary.txt
  exit 0
fi

cat > /app/cmd/reconcile/main.go <<'GO'
package main
import("encoding/csv";"fmt";"os";"path/filepath";"strconv";"strings")
type rec struct{id,party,scope,package_type,amount,ts,status,loc string; used bool}
type actrec struct{aid,id,party,scope,package_type,amount,ts,reason,loc string}
type win struct{scope,open,close,state string}
func readCSV(p string) []map[string]string{f,e:=os.Open(p); if e!=nil{panic(e)}; defer f.Close(); r:=csv.NewReader(f); rows,e:=r.ReadAll(); if e!=nil{panic(e)}; h:=rows[0]; out:=[]map[string]string{}; for _,row:=range rows[1:]{m:=map[string]string{}; for i,k:=range h{if i<len(row){m[strings.TrimSpace(k)]=strings.TrimSpace(row[i])}}; out=append(out,m)}; return out}
func digits(s string) bool{if len(s)!=14{return false}; for _,r:=range s{if r<'0'||r>'9'{return false}}; return true}
func canon(s string) string{return strings.ToUpper(strings.TrimSpace(s))}
func package_typeOK(s string) bool{return s=="CHEM"||s=="HEME"}
func reasonOK(s string) bool{return s=="SPLIT"||s=="TEMPBREACH"||s=="RECHECK"}
func windowOK(src rec, act actrec, ws []win) bool{if !digits(src.ts)||!digits(act.ts){return false}; for _,w:=range ws{if w.scope==src.scope&&w.state=="OPEN"&&digits(w.open)&&digits(w.close)&&src.ts>=w.open&&src.ts<=w.close&&act.ts>=src.ts&&act.ts<=w.close{return true}}; return false}
func main(){sources:=[]rec{}; for _,m:=range readCSV("/app/data/accessions.csv"){sources=append(sources,rec{m["shipment_id"],m["pharmacy_id"],m["chain_id"],canon(m["package_type"]),m["amount"],m["scan_ts"],m["status"],m["depot"],false})}; actions:=[]actrec{}; for _,m:=range readCSV("/app/data/exceptions.csv"){actions=append(actions,actrec{m["exception_id"],m["shipment_id"],m["pharmacy_id"],m["chain_id"],canon(m["package_type"]),m["amount"],m["exception_ts"],m["reason"],m["depot"]})}; windows:=[]win{}; for _,m:=range readCSV("/app/config/windows.csv"){windows=append(windows,win{m["chain_id"],m["open_ts"],m["close_ts"],m["state"]})}; os.MkdirAll("/app/out",0755); f,_:=os.Create("/app/out/coldchain_exception_report.csv"); defer f.Close(); w:=csv.NewWriter(f); defer w.Flush(); w.Write([]string{"exception_id","shipment_id","pharmacy_id","chain_id","package_type","amount","reason","status"}); mc,uc,ma,ua:=0,0,0,0; for _,act:=range actions{package_type:=act.package_type; best := -1
		for i, src := range sources {
			if src.id == act.id && src.amount == act.amount && !src.used && src.party == act.party && src.scope == act.scope && src.loc == act.loc && package_typeOK(src.package_type) && src.status == "RECEIVED" && src.package_type == package_type && reasonOK(act.reason) && windowOK(src, act, windows) {
				if best < 0 || src.ts > sources[best].ts { best = i }
			}
		}; amt,_:=strconv.Atoi(act.amount); if best>=0{sources[best].used = true; mc++; ma+=amt; w.Write([]string{act.aid,act.id,act.party,act.scope,sources[best].package_type,act.amount,act.reason,"MATCHED"})}else{uc++; ua+=amt; w.Write([]string{act.aid,act.id,act.party,act.scope,"",act.amount,act.reason,"UNMATCHED"})}}; os.WriteFile(filepath.Clean("/app/out/coldchain_exception_summary.txt"),[]byte(fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n",mc,ma,uc,ua)),0644)}
GO

/app/scripts/run_batch.sh
test -s /app/out/coldchain_exception_report.csv
test -s /app/out/coldchain_exception_summary.txt
