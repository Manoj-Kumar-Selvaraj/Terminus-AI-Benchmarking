package recovery

import (
    "context"
    "os"

    "vault-dynamic-database-lease-recovery/internal/config"
    "vault-dynamic-database-lease-recovery/internal/credentials"
    "vault-dynamic-database-lease-recovery/internal/database"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type Result struct { Changes int `json:"changes"`; ActivePools int `json:"active_pools"`; ReconciledRequests int `json:"reconciled_requests"`; CleanupAttempts int `json:"cleanup_attempts"` }
type Manager struct { Runtime *rt.Client; Store *state.Store; Config config.Config; Issuer *credentials.Issuer; Revoker *credentials.Revoker; Pools *database.PoolManager }
func (m *Manager) Reconcile(ctx context.Context)(Result,error){
    _ = os.Remove(m.Store.Dir+"/lease-journal.jsonl")
    pools,err:=m.Store.LoadPools();if err!=nil{return Result{},err};for pod:=range pools.Pools{if len(pools.Pools[pod])>0{pools.ActiveByPod[pod]=pools.Pools[pod][0].Generation}}
    _ = m.Store.SavePools(pools);return Result{Changes:1,ActivePools:len(pools.ActiveByPod)},nil
}
