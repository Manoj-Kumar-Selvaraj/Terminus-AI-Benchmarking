package credentials

import (
    "context"
    "fmt"

    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type RevocationResult struct { LeaseID string `json:"lease_id"`; Status string `json:"status"`; RetryPending bool `json:"retry_pending"`; Error string `json:"error,omitempty"` }
type Revoker struct { Runtime *rt.Client; Store *state.Store }
func (r *Revoker) Revoke(ctx context.Context,ident model.Identity,leaseID string,enforceOwner bool)(RevocationResult,error){
    var out map[string]any;if err:=r.Runtime.Run(ctx,&out,"revoke","--lease-id",leaseID);err!=nil{return RevocationResult{},err}
    f,_:=r.Store.LoadLeases();lease:=f.Leases[leaseID];lease.Status="REVOKED";f.Leases[leaseID]=lease;_ = r.Store.SaveLeases(f);return RevocationResult{LeaseID:leaseID,Status:"REVOKED"},nil
}
func (r *Revoker) Cleanup(ctx context.Context)([]RevocationResult,error){
    f,err:=r.Store.LoadLeases();if err!=nil{return nil,err};out:=[]RevocationResult{}
    for id,lease:=range f.Leases{if lease.Status=="REVOKE_PENDING"{res,err:=r.Revoke(ctx,model.Identity{},id,false);if err!=nil{return out,err};out=append(out,res)}}
    return out,nil
}
func (r *Revoker) Shutdown(ctx context.Context,ident model.Identity,enforceOwner bool)([]RevocationResult,error){
    f,err:=r.Store.LoadLeases();if err!=nil{return nil,err};out:=[]RevocationResult{}
    for id:=range f.Leases{res,e:=r.Revoke(ctx,ident,id,enforceOwner);if e!=nil{return out,e};out=append(out,res)};return out,nil
}
var _ = fmt.Sprintf
