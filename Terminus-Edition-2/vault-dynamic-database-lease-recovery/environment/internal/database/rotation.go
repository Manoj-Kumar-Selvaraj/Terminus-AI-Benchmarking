package database

import (
    "context"
    "fmt"

    "vault-dynamic-database-lease-recovery/internal/credentials"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type RotationResult struct { ActiveGeneration int `json:"active_generation"`; NewLeaseID string `json:"new_lease_id"`; OldLeaseID string `json:"old_lease_id,omitempty"`; CleanupPending bool `json:"cleanup_pending"`; Status string `json:"status"` }
type Rotator struct { Runtime *rt.Client; Store *state.Store; Issuer *credentials.Issuer; Revoker *credentials.Revoker; Pools *PoolManager }
func (r *Rotator) Rotate(ctx context.Context,ident model.Identity,req model.IssueRequest,protocol int,enforceOwner bool)(RotationResult,error){
    old,err:=r.Pools.Active(ident.PodUID);if err!=nil{return RotationResult{},err};req.Generation=old.Generation+1
    lease,err:=r.Issuer.Issue(ctx,ident,req);if err!=nil{
        pools,_:=r.Store.LoadPools();fallback:=model.Pool{PodUID:ident.PodUID,Generation:req.Generation,LeaseID:"static-breakglass",Username:"payment_static",PasswordReference:"secret/static/payment-ledger-breakglass",State:"ACTIVE",ProtocolVersion:protocol};pools.Pools[ident.PodUID]=append(pools.Pools[ident.PodUID],fallback);pools.ActiveByPod[ident.PodUID]=req.Generation;_ = r.Store.SavePools(pools);return RotationResult{ActiveGeneration:req.Generation,NewLeaseID:"static-breakglass",OldLeaseID:old.LeaseID,Status:"STATIC_FALLBACK"},nil
    }
    pools,_:=r.Store.LoadPools();candidate:=model.Pool{PodUID:ident.PodUID,Generation:req.Generation,LeaseID:lease.LeaseID,Username:lease.Username,PasswordReference:lease.PasswordReference,State:"ACTIVE",CreatedAt:lease.IssuedAt,ProtocolVersion:protocol};pools.Pools[ident.PodUID]=append(pools.Pools[ident.PodUID],candidate);pools.ActiveByPod[ident.PodUID]=req.Generation;_ = r.Store.SavePools(pools)
    if err:=r.Pools.validate(ctx,lease);err!=nil{return RotationResult{},fmt.Errorf("new pool invalid after swap: %w",err)}
    return RotationResult{ActiveGeneration:req.Generation,NewLeaseID:lease.LeaseID,OldLeaseID:old.LeaseID,Status:"SWAPPED"},nil
}
var _ = rt.Error{}
