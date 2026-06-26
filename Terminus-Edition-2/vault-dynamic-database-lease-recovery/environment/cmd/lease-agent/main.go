package main

import (
    "context"
    "encoding/json"
    "flag"
    "fmt"
    "os"
    "strings"

    "vault-dynamic-database-lease-recovery/internal/app"
    "vault-dynamic-database-lease-recovery/internal/kubernetesauth"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
)

type errorBody struct { Code string `json:"code"`; Message string `json:"message"`; Retryable bool `json:"retryable,omitempty"` }
func emit(value any){enc:=json.NewEncoder(os.Stdout);enc.SetEscapeHTML(false);_ = enc.Encode(value)}
func fail(err error){code:="APPLICATION_ERROR";message:=err.Error();retry:=false;if e,ok:=err.(*kubernetesauth.AuthError);ok{code=e.Code;message=e.Message}else if e,ok:=err.(*rt.Error);ok{code=e.Code;message=e.Message;retry=e.Retryable}else if n:=strings.Index(message,":");n>0{code=message[:n];message=strings.TrimSpace(message[n+1:])};emit(map[string]any{"ok":false,"error":errorBody{Code:code,Message:message,Retryable:retry}});os.Exit(2)}
func readRequest(path string)(model.IssueRequest,error){var req model.IssueRequest;raw,err:=os.ReadFile(path);if err!=nil{return req,err};err=json.Unmarshal(raw,&req);return req,err}
func main(){
    if len(os.Args)<2{fmt.Fprintln(os.Stderr,"usage: lease-agent <command>");os.Exit(2)};svc,err:=app.New();if err!=nil{fail(err)};ctx:=context.Background();cmd:=os.Args[1]
    switch cmd{
    case "login":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);token:=fs.String("token","","token file");_ = fs.Parse(os.Args[2:]);out,err:=svc.Login(ctx,*token);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "issue":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);token:=fs.String("token","","token file");request:=fs.String("request","","request file");version:=fs.Int("protocol",0,"protocol version");_ = fs.Parse(os.Args[2:]);req,err:=readRequest(*request);if err!=nil{fail(err)};out,err:=svc.Issue(ctx,*token,req,*version);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "renew":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);token:=fs.String("token","","token file");lease:=fs.String("lease-id","","lease id");version:=fs.Int("protocol",1,"protocol version");_ = fs.Parse(os.Args[2:]);out,err:=svc.Renew(ctx,*token,*lease,*version);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "rotate":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);token:=fs.String("token","","token file");request:=fs.String("request","","request file");version:=fs.Int("protocol",0,"protocol version");_ = fs.Parse(os.Args[2:]);req,err:=readRequest(*request);if err!=nil{fail(err)};out,err:=svc.Rotate(ctx,*token,req,*version);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "revoke":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);token:=fs.String("token","","token file");lease:=fs.String("lease-id","","lease id");_ = fs.Parse(os.Args[2:]);out,err:=svc.Revoke(ctx,*token,*lease);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "cleanup":out,err:=svc.Cleanup(ctx);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "shutdown":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);token:=fs.String("token","","token file");_ = fs.Parse(os.Args[2:]);out,err:=svc.Shutdown(ctx,*token);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "reconcile":out,err:=svc.Reconcile(ctx);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    default:fail(fmt.Errorf("UNKNOWN_COMMAND: %s",cmd))
    }
}
