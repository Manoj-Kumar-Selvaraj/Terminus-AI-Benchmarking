package database

import (
    "context"
    "fmt"

    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type PoolManager struct { Runtime *rt.Client; Store *state.Store }
func (p *PoolManager) validate(ctx context.Context, lease model.Lease) error { var out map[string]any;return p.Runtime.Run(ctx,&out,"validate-credential","--lease-id",lease.LeaseID,"--password-reference",lease.PasswordReference) }
func (p *PoolManager) EnsureInitial(ctx context.Context, lease model.Lease, protocol int) error {
    return p.Store.WithLock("pools-index",func() error {
        pools,err:=p.Store.LoadPools();if err!=nil{return err};if pools.ActiveByPod[lease.OwnerPodUID]>0{return nil}
        if err:=p.validate(ctx,lease);err!=nil{return err};pool:=model.Pool{PodUID:lease.OwnerPodUID,Generation:lease.Generation,LeaseID:lease.LeaseID,Username:lease.Username,PasswordReference:lease.PasswordReference,State:"ACTIVE",CreatedAt:lease.IssuedAt,ProtocolVersion:protocol}
        pools.Pools[lease.OwnerPodUID]=append(pools.Pools[lease.OwnerPodUID],pool);pools.ActiveByPod[lease.OwnerPodUID]=lease.Generation;return p.Store.SavePools(pools)
    })
}
func (p *PoolManager) Active(podUID string) (model.Pool,error) {
    pools,err:=p.Store.LoadPools();if err!=nil{return model.Pool{},err};gen:=pools.ActiveByPod[podUID];if gen==0{return model.Pool{},fmt.Errorf("NO_ACTIVE_POOL: no active pool for pod")}
    for _,pool:=range pools.Pools[podUID]{if pool.Generation==gen&&pool.State=="ACTIVE"{return pool,nil}}
    return model.Pool{},fmt.Errorf("NO_ACTIVE_POOL: active generation is unavailable")
}
func (p *PoolManager) Save(pools model.PoolFile) error { return p.Store.WithLock("pools-index",func() error{return p.Store.SavePools(pools)}) }
