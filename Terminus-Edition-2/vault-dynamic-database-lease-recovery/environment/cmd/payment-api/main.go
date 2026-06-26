package main

import (
    "context"
    "encoding/json"
    "flag"
    "fmt"
    "os"
    "strings"

    "vault-dynamic-database-lease-recovery/internal/database"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)
func emit(v any){_ = json.NewEncoder(os.Stdout).Encode(v)}
func fail(err error){code:="APPLICATION_ERROR";message:=err.Error();retry:=false;if e,ok:=err.(*rt.Error);ok{code=e.Code;message=e.Message;retry=e.Retryable}else if n:=strings.Index(message,":");n>0{code=message[:n];message=strings.TrimSpace(message[n+1:])};emit(map[string]any{"ok":false,"error":map[string]any{"code":code,"message":message,"retryable":retry}});os.Exit(2)}
func read(path string,out any)error{raw,err:=os.ReadFile(path);if err!=nil{return err};return json.Unmarshal(raw,out)}
func main(){if len(os.Args)<2{fmt.Fprintln(os.Stderr,"usage: payment-api <command>");os.Exit(2)};store:=state.New();runtime:=rt.New(store.Dir);pools:=&database.PoolManager{Runtime:runtime,Store:store};api:=&database.API{Runtime:runtime,Pools:pools};ctx:=context.Background();cmd:=os.Args[1]
    switch cmd{
    case "db-op":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);path:=fs.String("request","","request file");_ = fs.Parse(os.Args[2:]);var req database.OperationRequest;if err:=read(*path,&req);err!=nil{fail(err)};out,err:=api.Run(ctx,req);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "session-open":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);path:=fs.String("request","","request file");_ = fs.Parse(os.Args[2:]);var req database.OperationRequest;if err:=read(*path,&req);err!=nil{fail(err)};out,err:=api.SessionOpen(ctx,req);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "session-exec":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);path:=fs.String("request","","request file");_ = fs.Parse(os.Args[2:]);var req database.SessionExecRequest;if err:=read(*path,&req);err!=nil{fail(err)};out,err:=api.SessionExec(ctx,req);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    case "session-close":fs:=flag.NewFlagSet(cmd,flag.ExitOnError);id:=fs.String("session-id","","session id");_ = fs.Parse(os.Args[2:]);out,err:=api.SessionClose(ctx,*id);if err!=nil{fail(err)};emit(map[string]any{"ok":true,"result":out})
    default:fail(fmt.Errorf("UNKNOWN_COMMAND: %s",cmd))}
}
