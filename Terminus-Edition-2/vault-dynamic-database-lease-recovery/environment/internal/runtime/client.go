package runtime

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
)

type Error struct { Code string `json:"code"`; Message string `json:"message"`; Retryable bool `json:"retryable"` }
func (e *Error) Error() string { return e.Code+": "+e.Message }
type envelope struct { OK bool `json:"ok"`; Error *Error `json:"error,omitempty"` }
type Client struct { Binary string; RuntimeDir string; TempDir string }
func New(stateDir string) *Client {
    bin:=os.Getenv("VAULT_DB_RUNTIME_BIN"); if bin=="" {bin="/opt/task-tools/vault-db-runtime"}
    runtimeDir:=os.Getenv("VAULT_DB_RUNTIME_DIR"); if runtimeDir=="" {runtimeDir="/var/lib/vault-db-runtime"}
    return &Client{Binary:bin,RuntimeDir:runtimeDir,TempDir:filepath.Join(stateDir,".runtime-requests")}
}
func (c *Client) Run(ctx context.Context, out any, args ...string) error {
    cmd:=exec.CommandContext(ctx,c.Binary,args...); cmd.Env=append(os.Environ(),"VAULT_DB_RUNTIME_DIR="+c.RuntimeDir)
    var stdout,stderr bytes.Buffer; cmd.Stdout=&stdout; cmd.Stderr=&stderr
    err:=cmd.Run(); raw:=bytes.TrimSpace(stdout.Bytes())
    if len(raw)==0 { if err!=nil{return fmt.Errorf("runtime command failed: %w: %s",err,stderr.String())}; return fmt.Errorf("runtime returned no response") }
    var env envelope
    if uerr:=json.Unmarshal(raw,&env);uerr!=nil{return fmt.Errorf("decode runtime response: %w (%s)",uerr,string(raw))}
    if !env.OK { if env.Error!=nil{return env.Error}; return fmt.Errorf("runtime rejected request") }
    if out!=nil { if uerr:=json.Unmarshal(raw,out);uerr!=nil{return fmt.Errorf("decode runtime payload: %w",uerr)} }
    return nil
}
func (c *Client) Request(ctx context.Context, payload any, out any, prefix string, args ...string) error {
    if err:=os.MkdirAll(c.TempDir,0700);err!=nil{return err}
    raw,err:=json.Marshal(payload);if err!=nil{return err}
    f,err:=os.CreateTemp(c.TempDir,prefix+"-*.json");if err!=nil{return err}
    name:=f.Name();defer os.Remove(name)
    if err:=f.Chmod(0600);err!=nil{f.Close();return err}
    if _,err:=f.Write(raw);err!=nil{f.Close();return err};if err:=f.Close();err!=nil{return err}
    args=append(args,"--request",name);return c.Run(ctx,out,args...)
}
