package credentials

import (
    "context"
    "fmt"
    "time"

    "vault-dynamic-database-lease-recovery/internal/clock"
    "vault-dynamic-database-lease-recovery/internal/config"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type RenewalResult struct { Action string `json:"action"`; Lease model.Lease `json:"lease,omitempty"`; Attempts int `json:"attempts"`; BackoffSeconds []int `json:"backoff_seconds,omitempty"`; Usable bool `json:"usable"`; Reason string `json:"reason,omitempty"` }
type Renewer struct { Runtime *rt.Client; Store *state.Store; Config config.Config; Clock clock.Clock; Issuer *Issuer }
func (r *Renewer) Maintain(ctx context.Context, ident model.Identity, leaseID string, enforceOwner bool) (RenewalResult,error) {
    f,err:=r.Store.LoadLeases();if err!=nil{return RenewalResult{},err};lease,ok:=f.Leases[leaseID];if !ok{return RenewalResult{},fmt.Errorf("UNKNOWN_LEASE: lease does not exist")}
    now:=time.Now().UTC();target:=now.Add(time.Duration(r.Config.Lease.DefaultTTLSeconds)*time.Second).Format(time.RFC3339)
    var renewed model.Lease;op:="renew-"+time.Now().Format("150405.000000000")
    if err:=r.Runtime.Run(ctx,&renewed,"renew","--lease-id",leaseID,"--operation-id",op,"--target-expires-at",target);err!=nil{
        req:=model.IssueRequest{RequestID:"replacement-"+lease.RequestID+"-"+op,PodUID:ident.PodUID,VaultRole:ident.VaultRole,DatabaseRole:"payment-ledger",RequestedAt:now.Format(time.RFC3339),Generation:lease.Generation+1}
        replacement,e:=r.Issuer.Issue(ctx,ident,req);if e!=nil{return RenewalResult{},err};return RenewalResult{Action:"REISSUED",Lease:replacement,Attempts:1,Usable:true},nil
    }
    normalizeLease(&renewed);f.Leases[leaseID]=renewed;_ = r.Store.SaveLeases(f);return RenewalResult{Action:"RENEWED",Lease:renewed,Attempts:1,Usable:true},nil
}
