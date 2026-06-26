package state

import (
    "bufio"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "errors"
    "fmt"
    "os"
    "path/filepath"
    "strings"
    "syscall"

    "vault-dynamic-database-lease-recovery/internal/model"
)

type Store struct { Dir string }
func New() *Store { d:=os.Getenv("LEASE_AGENT_STATE_DIR");if d==""{d="/app/state"};return &Store{Dir:d} }
func (s *Store) ensure() error { return os.MkdirAll(s.Dir,0700) }
func (s *Store) path(name string) string { return filepath.Join(s.Dir,name) }
func atomicWrite(path string, raw []byte) error {
    if err:=os.MkdirAll(filepath.Dir(path),0700);err!=nil{return err}
    f,err:=os.CreateTemp(filepath.Dir(path),".state-*.tmp");if err!=nil{return err};name:=f.Name();defer os.Remove(name)
    if err:=f.Chmod(0600);err!=nil{f.Close();return err}
    if _,err:=f.Write(raw);err!=nil{f.Close();return err};if err:=f.Sync();err!=nil{f.Close();return err};if err:=f.Close();err!=nil{return err}
    return os.Rename(name,path)
}
func (s *Store) writeJSON(name string, value any) error { raw,err:=json.MarshalIndent(value,"","  ");if err!=nil{return err};raw=append(raw,'\n');return atomicWrite(s.path(name),raw) }
func (s *Store) readJSON(name string, value any) error {
    raw,err:=os.ReadFile(s.path(name));if errors.Is(err,os.ErrNotExist){return nil};if err!=nil{return err};if len(strings.TrimSpace(string(raw)))==0{return nil};return json.Unmarshal(raw,value)
}
func (s *Store) LoadLeases() (model.LeaseFile,error) { out:=model.LeaseFile{Leases:map[string]model.Lease{}};err:=s.readJSON("active-leases.json",&out);if out.Leases==nil{out.Leases=map[string]model.Lease{}};return out,err }
func (s *Store) SaveLeases(v model.LeaseFile) error { return s.writeJSON("active-leases.json",v) }
func (s *Store) LoadPools() (model.PoolFile,error) { out:=model.PoolFile{ActiveByPod:map[string]int{},Pools:map[string][]model.Pool{}};err:=s.readJSON("connection-pools.json",&out);if out.ActiveByPod==nil{out.ActiveByPod=map[string]int{}};if out.Pools==nil{out.Pools=map[string][]model.Pool{}};return out,err }
func (s *Store) SavePools(v model.PoolFile) error { return s.writeJSON("connection-pools.json",v) }
func (s *Store) LoadRequests() (model.RequestFile,error) { out:=model.RequestFile{Requests:map[string]model.RequestRecord{}};err:=s.readJSON("issuance-requests.json",&out);if out.Requests==nil{out.Requests=map[string]model.RequestRecord{}};return out,err }
func (s *Store) SaveRequests(v model.RequestFile) error { return s.writeJSON("issuance-requests.json",v) }
func (s *Store) LoadCheckpoint() (model.Checkpoint,error) { var out model.Checkpoint;err:=s.readJSON("recovery-checkpoint.json",&out);return out,err }
func (s *Store) SaveCheckpoint(v model.Checkpoint) error { return s.writeJSON("recovery-checkpoint.json",v) }
func lockName(key string) string { h:=sha256.Sum256([]byte(key));return hex.EncodeToString(h[:12])+".lock" }
func (s *Store) WithLock(key string, fn func() error) error {
    if err:=s.ensure();err!=nil{return err};dir:=s.path(".locks");if err:=os.MkdirAll(dir,0700);err!=nil{return err}
    f,err:=os.OpenFile(filepath.Join(dir,lockName(key)),os.O_CREATE|os.O_RDWR,0600);if err!=nil{return err};defer f.Close()
    if err:=syscall.Flock(int(f.Fd()),syscall.LOCK_EX);err!=nil{return err};defer syscall.Flock(int(f.Fd()),syscall.LOCK_UN)
    return fn()
}
func (s *Store) AppendJournal(event map[string]any) error {
    return s.WithLock("journal",func() error {
        if err:=s.ensure();err!=nil{return err};raw,err:=json.Marshal(event);if err!=nil{return err}
        f,err:=os.OpenFile(s.path("lease-journal.jsonl"),os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600);if err!=nil{return err};defer f.Close()
        if _,err:=f.Write(append(raw,'\n'));err!=nil{return err};return f.Sync()
    })
}
func (s *Store) LoadJournal(recoverTail bool) ([]map[string]any,error) {
    path:=s.path("lease-journal.jsonl");raw,err:=os.ReadFile(path);if errors.Is(err,os.ErrNotExist){return nil,nil};if err!=nil{return nil,err}
    lines:=strings.Split(string(raw),"\n");out:=make([]map[string]any,0,len(lines));validBytes:=0
    scanner:=bufio.NewScanner(strings.NewReader(string(raw)));lineNo:=0
    for scanner.Scan(){lineNo++;line:=scanner.Text();if strings.TrimSpace(line)==""{validBytes+=len(line)+1;continue};var event map[string]any
        if err:=json.Unmarshal([]byte(line),&event);err!=nil{
            isLastNonEmpty:=true;for _,rest:=range lines[lineNo:]{if strings.TrimSpace(rest)!=""{isLastNonEmpty=false;break}}
            if recoverTail&&isLastNonEmpty{if err:=atomicWrite(path,raw[:validBytes]);err!=nil{return nil,err};return out,nil}
            return nil,fmt.Errorf("malformed committed journal line %d: %w",lineNo,err)
        }
        out=append(out,event);validBytes+=len(line)+1
    }
    if err:=scanner.Err();err!=nil{return nil,err};return out,nil
}
func Fingerprint(req model.IssueRequest) string { h:=sha256.Sum256([]byte(req.RequestID+"|"+req.PodUID+"|"+req.VaultRole+"|"+req.DatabaseRole));return hex.EncodeToString(h[:]) }
