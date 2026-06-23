package main
import("encoding/csv";"fmt";"os";"path/filepath";"strconv";"strings")
type rec struct{id,party,scope,hold_type,amount,ts,status,loc string; used bool}
type actrec struct{aid,id,party,scope,hold_type,amount,ts,reason,loc string}
type win struct{scope,open,close,state string}
func readCSV(p string) []map[string]string{f,e:=os.Open(p); if e!=nil{panic(e)}; defer f.Close(); r:=csv.NewReader(f); rows,e:=r.ReadAll(); if e!=nil{panic(e)}; h:=rows[0]; out:=[]map[string]string{}; for _,row:=range rows[1:]{m:=map[string]string{}; for i,k:=range h{if i<len(row){m[strings.TrimSpace(k)]=strings.TrimSpace(row[i])}}; out=append(out,m)}; return out}
func digits(s string) bool{if len(s)!=14{return false}; for _,r:=range s{if r<'0'||r>'9'{return false}}; return true}
func canon(s string) string{switch strings.ToUpper(strings.TrimSpace(s)){case "HT", "HOT": return "HOT"
case "WM", "WARM": return "WARM"
case "CL", "COLD": return "COLD"
default: return strings.ToUpper(strings.TrimSpace(s))}}
func reasonOK(s string) bool{return s=="DECOMM"||s=="MIGRATE"||s=="OVERRIDE"}
func windowOK(src rec, act actrec, ws []win) bool{if !digits(src.ts)||!digits(act.ts){return false}; for _,w:=range ws{if w.scope==src.scope&&w.state=="OPEN"&&digits(w.open)&&digits(w.close)&&src.ts>=w.open&&src.ts<=w.close&&act.ts>=src.ts&&act.ts<=w.close{return true}}; return false}
func main(){sources:=[]rec{}; for _,m:=range readCSV("/app/data/holds.csv"){sources=append(sources,rec{m["hold_id"],m["asset_id"],m["aisle_id"],canon(m["access_tier"]),m["amount"],m["hold_ts"],m["status"],m["rack"],false})}; actions:=[]actrec{}; for _,m:=range readCSV("/app/data/releases.csv"){actions=append(actions,actrec{m["release_id"],m["hold_id"],m["asset_id"],m["aisle_id"],canon(m["access_tier"]),m["amount"],m["release_ts"],m["reason"],m["rack"]})}; windows:=[]win{}; for _,m:=range readCSV("/app/config/windows.csv"){windows=append(windows,win{m["aisle_id"],m["open_ts"],m["close_ts"],m["state"]})}; os.MkdirAll("/app/out",0755); f,_:=os.Create("/app/out/rack_release_report.csv"); defer f.Close(); w:=csv.NewWriter(f); defer w.Flush(); w.Write([]string{"release_id","hold_id","asset_id","aisle_id","access_tier","amount","reason","status"}); mc,uc,ma,ua:=0,0,0,0; for _,act:=range actions{hold_type:=act.hold_type; best := -1
		for i, src := range sources {
			if (strings.HasPrefix(src.id, act.id) || strings.HasPrefix(act.id, src.id)) && src.amount == act.amount {
				if best < 0 || src.ts > sources[best].ts { best = i }
			}
		}; amt,_:=strconv.Atoi(act.amount); if best>=0{mc++; ma-=amt; w.Write([]string{act.aid,act.id,act.party,act.scope,sources[best].hold_type,act.amount,act.reason,"MATCHED"})}else{uc++; ua+=amt; w.Write([]string{act.aid,act.id,act.party,act.scope,"",act.amount,act.reason,"UNMATCHED"})}}; os.WriteFile(filepath.Clean("/app/out/rack_release_summary.txt"),[]byte(fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n",mc,ma,uc,ua)),0644)}