package logging

import (
    "encoding/json"
    "os"
    "path/filepath"
    "strings"
    "sync"
)
var mu sync.Mutex
func Event(name string, fields map[string]any) {
    path:=os.Getenv("LEASE_AGENT_LOG");if path==""{path="/app/logs/lease-agent.jsonl"}
    _=os.MkdirAll(filepath.Dir(path),0700);event:=map[string]any{"event":name}
    for k,v:=range fields { lk:=strings.ToLower(k);if strings.Contains(lk,"token")||strings.Contains(lk,"password"){event[k]="<redacted>"}else{event[k]=v} }
    raw,_:=json.Marshal(event);mu.Lock();defer mu.Unlock();f,err:=os.OpenFile(path,os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600);if err==nil{_,_=f.Write(append(raw,'\n'));_=f.Close()}
}
