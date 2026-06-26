package credentials

import (
    "context"
    "fmt"

    "vault-dynamic-database-lease-recovery/internal/config"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type Issuer struct { Runtime *rt.Client; Store *state.Store; Config config.Config }
func normalizeLease(l *model.Lease) { if l.DatabaseUsername==""{l.DatabaseUsername=l.Username};if l.Username==""{l.Username=l.DatabaseUsername};if l.Status==""{l.Status="ACTIVE"} }
func (i *Issuer) persist(lease model.Lease) error {
    return i.Store.WithLock("leases-index",func() error { f,err:=i.Store.LoadLeases();if err!=nil{return err};f.Leases[lease.LeaseID]=lease;return i.Store.SaveLeases(f) })
}
func (i *Issuer) Issue(ctx context.Context, ident model.Identity, req model.IssueRequest) (model.Lease,error) {
    if req.RequestID==""||req.PodUID==""{return model.Lease{},fmt.Errorf("INVALID_REQUEST: request_id and pod_uid are required")}
    if req.VaultRole==""{req.VaultRole=ident.VaultRole};if req.DatabaseRole==""{req.DatabaseRole="payment-ledger"};if req.Generation<=0{req.Generation=1}
    req.VaultNode=i.Config.Failover.Nodes[0];req.VaultEpoch=1
    attempts:=i.Config.Failover.MaximumIssueAttempts;if attempts<=0{attempts=1}
    var last error
    for n:=0;n<attempts;n++ {
        var lease model.Lease;err:=i.Runtime.Request(ctx,req,&lease,"issue","issue")
        if err==nil { normalizeLease(&lease);if err:=i.persist(lease);err!=nil{return model.Lease{},err};_ = i.Store.AppendJournal(map[string]any{"event":"LEASE_ISSUED","request_id":req.RequestID,"lease_id":lease.LeaseID,"username":lease.Username,"status":"ACTIVE"});return lease,nil }
        last=err
        if re,ok:=err.(*rt.Error);!ok||!re.Retryable{break}
    }
    return model.Lease{},last
}
