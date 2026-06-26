#!/usr/bin/env bash
set -Eeuo pipefail

cd /app

cat > internal/kubernetesauth/login.go <<'EOF'

package kubernetesauth

import (
    "context"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "os"
    "strings"
    "time"

    "vault-dynamic-database-lease-recovery/internal/clock"
    "vault-dynamic-database-lease-recovery/internal/config"
    "vault-dynamic-database-lease-recovery/internal/logging"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
)

type Authenticator struct { Config config.KubernetesAuth; Runtime *rt.Client; Clock clock.Clock }
type validation struct { Claims json.RawMessage `json:"claims"` }
type AuthError struct { Code string; Message string }
func (e *AuthError) Error() string { return e.Code+": "+e.Message }
func deny(code string) error { return &AuthError{Code:code,Message:"workload identity was not authorized"} }
func audiences(raw json.RawMessage) ([]string,error) {
    var one string;if err:=json.Unmarshal(raw,&one);err==nil{return []string{one},nil}
    var many []string;if err:=json.Unmarshal(raw,&many);err==nil{return many,nil}
    return nil,fmt.Errorf("invalid audience")
}
func contains(values []string,want string) bool { for _,v:=range values{if v==want{return true}};return false }
func (a *Authenticator) Login(ctx context.Context, tokenPath string) (model.Identity,error) {
    raw,err:=os.ReadFile(tokenPath);if err!=nil{return model.Identity{},deny("EMPTY_TOKEN")};token:=strings.TrimSpace(string(raw));if token==""{return model.Identity{},deny("EMPTY_TOKEN")}
    var checked validation
    if err:=a.Runtime.Run(ctx,&checked,"validate-token","--token",token);err!=nil{
        if re,ok:=err.(*rt.Error);ok{return model.Identity{},deny(re.Code)};return model.Identity{},err
    }
    var claims model.Claims;if err:=json.Unmarshal(checked.Claims,&claims);err!=nil{return model.Identity{},deny("MISSING_CLAIM")}
    if claims.Issuer==""||claims.Subject==""||len(claims.Audience)==0||claims.Namespace==""||claims.ServiceAccount==""||claims.PodUID==""||claims.Expires==0{return model.Identity{},deny("MISSING_CLAIM")}
    if claims.Issuer!=a.Config.Issuer{return model.Identity{},deny("INVALID_ISSUER")}
    aud,err:=audiences(claims.Audience);if err!=nil||!contains(aud,a.Config.Audience){return model.Identity{},deny("INVALID_AUDIENCE")}
    now,err:=a.Clock.Now(ctx);if err!=nil{return model.Identity{},err}
    if now.Unix()>=claims.Expires{return model.Identity{},deny("TOKEN_EXPIRED")}
    if claims.NotBefore!=0&&now.Unix()<claims.NotBefore{return model.Identity{},deny("TOKEN_NOT_YET_VALID")}
    parts:=strings.Split(claims.Subject,":")
    if len(parts)!=4||parts[0]!="system"||parts[1]!="serviceaccount"||parts[2]==""||parts[3]==""{return model.Identity{},deny("MALFORMED_SUBJECT")}
    if parts[2]!=claims.Namespace||parts[3]!=claims.ServiceAccount{return model.Identity{},deny("MALFORMED_SUBJECT")}
    if claims.Namespace!=a.Config.Namespace{return model.Identity{},deny("WRONG_NAMESPACE")}
    if claims.ServiceAccount!=a.Config.ServiceAccount{return model.Identity{},deny("WRONG_SERVICE_ACCOUNT")}
    expected:="system:serviceaccount:"+a.Config.Namespace+":"+a.Config.ServiceAccount
    if claims.Subject!=expected{return model.Identity{},deny("MALFORMED_SUBJECT")}
    sum:=sha256.Sum256([]byte(token));accessor:=hex.EncodeToString(sum[:12])
    ident:=model.Identity{Namespace:claims.Namespace,ServiceAccount:claims.ServiceAccount,PodUID:claims.PodUID,VaultRole:a.Config.VaultRole,Accessor:accessor}
    logging.Event("kubernetes_login",map[string]any{"pod_uid":ident.PodUID,"accessor":accessor,"result":"accepted","at":now.Format(time.RFC3339)})
    return ident,nil
}
EOF

cat > internal/credentials/renewal.go <<'EOF'

package credentials

import (
    "context"
    "crypto/sha256"
    "encoding/hex"
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
func renewalOperation(leaseID,target string) string { h:=sha256.Sum256([]byte(leaseID+"|"+target));return "renew-"+hex.EncodeToString(h[:12]) }
func (r *Renewer) saveLease(lease model.Lease) error { return r.Store.WithLock("leases-index",func() error { f,err:=r.Store.LoadLeases();if err!=nil{return err};f.Leases[lease.LeaseID]=lease;return r.Store.SaveLeases(f) }) }
func (r *Renewer) Maintain(ctx context.Context, ident model.Identity, leaseID string, enforceOwner bool) (RenewalResult,error) {
    f,err:=r.Store.LoadLeases();if err!=nil{return RenewalResult{},err};lease,ok:=f.Leases[leaseID];if !ok{return RenewalResult{},fmt.Errorf("UNKNOWN_LEASE: lease does not exist")}
    if enforceOwner&&lease.OwnerPodUID!=ident.PodUID{return RenewalResult{},fmt.Errorf("LEASE_OWNERSHIP_DENIED: lease belongs to another pod")}
    now,err:=r.Clock.Now(ctx);if err!=nil{return RenewalResult{},err}
    checkpoint,err:=r.Store.LoadCheckpoint();if err!=nil{return RenewalResult{},err};if checkpoint.LastClock!=""{last,e:=time.Parse(time.RFC3339,checkpoint.LastClock);if e!=nil{return RenewalResult{},fmt.Errorf("MALFORMED_CHECKPOINT: invalid last clock")};if now.Before(last){return RenewalResult{},fmt.Errorf("CLOCK_REGRESSION: runtime clock moved backwards")}}
    checkpoint.LastClock=now.Format(time.RFC3339);if err:=r.Store.SaveCheckpoint(checkpoint);err!=nil{return RenewalResult{},err}
    expires,err:=time.Parse(time.RFC3339,lease.ExpiresAt);if err!=nil{return RenewalResult{},fmt.Errorf("MALFORMED_LEASE: invalid expires_at")};maximum,err:=time.Parse(time.RFC3339,lease.MaxExpiresAt);if err!=nil{return RenewalResult{},fmt.Errorf("MALFORMED_LEASE: invalid max_expires_at")}
    if lease.Status=="REVOKED"{return RenewalResult{},fmt.Errorf("LEASE_REVOKED: revoked lease cannot renew")}
    if !now.Before(expires){lease.Status="EXPIRED";_ = r.saveLease(lease);return RenewalResult{Action:"EXPIRED",Lease:lease,Usable:false,Reason:"lease expiry reached"},nil}
    if enforceOwner {
        pools,err:=r.Store.LoadPools();if err!=nil{return RenewalResult{},err};if active:=pools.ActiveByPod[ident.PodUID];active>lease.Generation{return RenewalResult{},fmt.Errorf("SUPERSEDED_LEASE: stale generation cannot renew")}
    }
    if !lease.Renewable{return RenewalResult{Action:"ROTATION_REQUIRED",Lease:lease,Usable:true,Reason:"lease is not renewable"},nil}
    window:=time.Duration(r.Config.Lease.RenewalWindowSeconds)*time.Second
    if now.Before(expires.Add(-window)){return RenewalResult{Action:"NO_ACTION",Lease:lease,Usable:true,Reason:"outside renewal window"},nil}
    if lease.LastRenewedAt!=""{last,err:=time.Parse(time.RFC3339,lease.LastRenewedAt);if err!=nil{return RenewalResult{},fmt.Errorf("MALFORMED_LEASE: invalid last_renewed_at")};minimum:=time.Duration(r.Config.Lease.MinimumRenewalIntervalSeconds)*time.Second;if now.Sub(last)<minimum{return RenewalResult{Action:"NO_ACTION",Lease:lease,Usable:true,Reason:"minimum renewal interval"},nil}}
    target:=now.Add(time.Duration(r.Config.Lease.DefaultTTLSeconds)*time.Second);if target.After(maximum){target=maximum}
    if !target.After(expires){return RenewalResult{Action:"ROTATION_REQUIRED",Lease:lease,Usable:true,Reason:"maximum ttl reached"},nil}
    op:=renewalOperation(leaseID,target.Format(time.RFC3339));attempts:=r.Config.Lease.MaxRenewalAttempts;if attempts<=0{attempts=1};backoff:=[]int{};var lastErr error
    for n:=0;n<attempts;n++ {
        var renewed model.Lease;err:=r.Runtime.Run(ctx,&renewed,"renew","--lease-id",leaseID,"--operation-id",op,"--target-expires-at",target.Format(time.RFC3339));if err==nil{
            normalizeLease(&renewed);if renewed.LeaseID!=lease.LeaseID||renewed.DatabaseUsername!=lease.DatabaseUsername{return RenewalResult{},fmt.Errorf("RENEWAL_IDENTITY_CHANGED: runtime changed lease identity")}
            if timeValue,e:=time.Parse(time.RFC3339,renewed.ExpiresAt);e!=nil||timeValue.After(maximum){return RenewalResult{},fmt.Errorf("MAX_TTL_VIOLATION: renewal exceeded maximum ttl")}
            if err:=r.saveLease(renewed);err!=nil{return RenewalResult{},err};_ = r.Store.AppendJournal(map[string]any{"event":"RENEWED","lease_id":leaseID,"operation_id":op,"expires_at":renewed.ExpiresAt,"attempts":n+1})
            return RenewalResult{Action:"RENEWED",Lease:renewed,Attempts:n+1,BackoffSeconds:backoff,Usable:true},nil
        }
        lastErr=err;re,ok:=err.(*rt.Error);if !ok||!re.Retryable{return RenewalResult{},err};if n+1<attempts{delay:=1;if n<len(r.Config.Lease.RetryBackoffSeconds){delay=r.Config.Lease.RetryBackoffSeconds[n]};backoff=append(backoff,delay);_ = r.Store.AppendJournal(map[string]any{"event":"RENEW_RETRY","lease_id":leaseID,"operation_id":op,"attempt":n+1,"backoff_seconds":delay})}
    }
    usable:=now.Before(expires);_ = r.Store.AppendJournal(map[string]any{"event":"RENEW_PENDING","lease_id":leaseID,"operation_id":op,"attempts":attempts,"usable":usable})
    return RenewalResult{Action:"RETRY_PENDING",Lease:lease,Attempts:attempts,BackoffSeconds:backoff,Usable:usable,Reason:fmt.Sprint(lastErr)},nil
}
EOF

cat > internal/credentials/revocation.go <<'EOF'

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
func (r *Revoker) update(lease model.Lease) error{return r.Store.WithLock("leases-index",func()error{f,err:=r.Store.LoadLeases();if err!=nil{return err};f.Leases[lease.LeaseID]=lease;return r.Store.SaveLeases(f)})}
func (r *Revoker) Revoke(ctx context.Context,ident model.Identity,leaseID string,enforceOwner bool)(RevocationResult,error){
    f,err:=r.Store.LoadLeases();if err!=nil{return RevocationResult{},err};lease,ok:=f.Leases[leaseID]
    if !ok{return RevocationResult{LeaseID:leaseID,Status:"REVOKED"},nil}
    if enforceOwner&&lease.OwnerPodUID!=ident.PodUID{return RevocationResult{},fmt.Errorf("LEASE_OWNERSHIP_DENIED: lease belongs to another pod")}
    if lease.Status=="REVOKED"{return RevocationResult{LeaseID:leaseID,Status:"REVOKED"},nil}
    var out map[string]any;if err:=r.Runtime.Run(ctx,&out,"revoke","--lease-id",leaseID);err!=nil{
        if re,ok:=err.(*rt.Error);ok&&re.Retryable{lease.Status="REVOKE_PENDING";if uerr:=r.update(lease);uerr!=nil{return RevocationResult{},uerr};_ = r.Store.AppendJournal(map[string]any{"event":"REVOKE_PENDING","lease_id":leaseID,"error":re.Code});return RevocationResult{LeaseID:leaseID,Status:"REVOKE_PENDING",RetryPending:true,Error:re.Code},nil};return RevocationResult{},err
    }
    lease.Status="REVOKED";if err:=r.update(lease);err!=nil{return RevocationResult{},err};_ = r.Store.AppendJournal(map[string]any{"event":"REVOKED","lease_id":leaseID});return RevocationResult{LeaseID:leaseID,Status:"REVOKED"},nil
}
func (r *Revoker) Cleanup(ctx context.Context)([]RevocationResult,error){
    f,err:=r.Store.LoadLeases();if err!=nil{return nil,err};results:=[]RevocationResult{};var hard error
    for id,lease:=range f.Leases{if lease.Status!="REVOKE_PENDING"{continue};res,e:=r.Revoke(ctx,model.Identity{},id,false);if e!=nil{hard=e;results=append(results,RevocationResult{LeaseID:id,Status:"FAILED",Error:e.Error()});continue};results=append(results,res)}
    return results,hard
}
func (r *Revoker) Shutdown(ctx context.Context,ident model.Identity,enforceOwner bool)([]RevocationResult,error){
    f,err:=r.Store.LoadLeases();if err!=nil{return nil,err};results:=[]RevocationResult{};var hard error
    for id,lease:=range f.Leases{if lease.OwnerPodUID!=ident.PodUID||lease.Status=="REVOKED"{continue};res,e:=r.Revoke(ctx,ident,id,enforceOwner);if e!=nil{hard=e;continue};results=append(results,res)}
    return results,hard
}
EOF

cat > internal/database/rotation.go <<'EOF'

package database

import (
    "context"
    "fmt"
    "time"

    "vault-dynamic-database-lease-recovery/internal/credentials"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type RotationResult struct { ActiveGeneration int `json:"active_generation"`; NewLeaseID string `json:"new_lease_id"`; OldLeaseID string `json:"old_lease_id,omitempty"`; CleanupPending bool `json:"cleanup_pending"`; Status string `json:"status"` }
type Rotator struct { Runtime *rt.Client; Store *state.Store; Issuer *credentials.Issuer; Revoker *credentials.Revoker; Pools *PoolManager }
func (r *Rotator) fault(ctx context.Context,point string,req model.IssueRequest,leaseID string) error { var out map[string]any;args:=[]string{"fault-check","--point",point};if req.RequestID!=""{args=append(args,"--request-id",req.RequestID)};if leaseID!=""{args=append(args,"--lease-id",leaseID)};if req.PodUID!=""{args=append(args,"--pod-uid",req.PodUID)};return r.Runtime.Run(ctx,&out,args...) }
func (r *Rotator) removeCandidate(pod string,generation int) error{return r.Store.WithLock("pools-index",func()error{p,err:=r.Store.LoadPools();if err!=nil{return err};kept:=[]model.Pool{};for _,x:=range p.Pools[pod]{if x.Generation!=generation{kept=append(kept,x)}};p.Pools[pod]=kept;return r.Store.SavePools(p)})}
func (r *Rotator) Rotate(ctx context.Context,ident model.Identity,req model.IssueRequest,protocol int,enforceOwner bool)(RotationResult,error){
    old,err:=r.Pools.Active(ident.PodUID);if err!=nil{return RotationResult{},err};req.Generation=old.Generation+1;req.PodUID=ident.PodUID
    lease,err:=r.Issuer.Issue(ctx,ident,req);if err!=nil{return RotationResult{},err}
    if err:=r.fault(ctx,"POOL_CREATE",req,lease.LeaseID);err!=nil{_,_=r.Revoker.Revoke(ctx,ident,lease.LeaseID,false);return RotationResult{},err}
    candidate:=model.Pool{PodUID:ident.PodUID,Generation:req.Generation,LeaseID:lease.LeaseID,Username:lease.Username,PasswordReference:lease.PasswordReference,State:"CANDIDATE",CreatedAt:lease.IssuedAt,ProtocolVersion:protocol}
    if err:=r.Store.WithLock("pools-index",func()error{p,err:=r.Store.LoadPools();if err!=nil{return err};p.Pools[ident.PodUID]=append(p.Pools[ident.PodUID],candidate);return r.Store.SavePools(p)});err!=nil{return RotationResult{},err}
    if err:=r.Pools.validate(ctx,lease);err!=nil{_ = r.removeCandidate(ident.PodUID,req.Generation);_,_=r.Revoker.Revoke(ctx,ident,lease.LeaseID,false);return RotationResult{},fmt.Errorf("POOL_VALIDATION_FAILED: %w",err)}
    if err:=r.fault(ctx,"BEFORE_POOL_SWAP",req,lease.LeaseID);err!=nil{_ = r.removeCandidate(ident.PodUID,req.Generation);_,_=r.Revoker.Revoke(ctx,ident,lease.LeaseID,false);return RotationResult{},err}
    now,err:=time.Parse(time.RFC3339,lease.IssuedAt);if err!=nil{return RotationResult{},err};deadline:=now.Add(45*time.Second).Format(time.RFC3339)
    if err:=r.Store.WithLock("pools-index",func()error{p,err:=r.Store.LoadPools();if err!=nil{return err};items:=p.Pools[ident.PodUID];for n:=range items{if items[n].Generation==old.Generation{items[n].State="DRAINING";items[n].DrainDeadline=deadline};if items[n].Generation==candidate.Generation{items[n].State="ACTIVE"}};p.Pools[ident.PodUID]=items;p.ActiveByPod[ident.PodUID]=candidate.Generation;return r.Store.SavePools(p)});err!=nil{return RotationResult{},err}
    _ = r.Store.AppendJournal(map[string]any{"event":"POOL_SWAPPED","pod_uid":ident.PodUID,"old_generation":old.Generation,"new_generation":candidate.Generation,"old_lease_id":old.LeaseID,"new_lease_id":lease.LeaseID})
    if err:=r.fault(ctx,"AFTER_POOL_SWAP",req,lease.LeaseID);err!=nil{return RotationResult{},err}
    revoked,err:=r.Revoker.Revoke(ctx,ident,old.LeaseID,enforceOwner);if err!=nil{return RotationResult{},err};pending:=revoked.RetryPending
    if !pending{_ = r.Store.WithLock("pools-index",func()error{p,e:=r.Store.LoadPools();if e!=nil{return e};items:=p.Pools[ident.PodUID];for n:=range items{if items[n].Generation==old.Generation{items[n].State="RETIRED"}};p.Pools[ident.PodUID]=items;return r.Store.SavePools(p)})}
    return RotationResult{ActiveGeneration:candidate.Generation,NewLeaseID:lease.LeaseID,OldLeaseID:old.LeaseID,CleanupPending:pending,Status:"ACTIVE"},nil
}
EOF

cat > internal/recovery/reconcile.go <<'EOF'

package recovery

import (
    "context"
    "sort"

    "vault-dynamic-database-lease-recovery/internal/config"
    "vault-dynamic-database-lease-recovery/internal/credentials"
    "vault-dynamic-database-lease-recovery/internal/database"
    "vault-dynamic-database-lease-recovery/internal/model"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type Result struct { Changes int `json:"changes"`; ActivePools int `json:"active_pools"`; ReconciledRequests int `json:"reconciled_requests"`; CleanupAttempts int `json:"cleanup_attempts"` }
type Manager struct { Runtime *rt.Client; Store *state.Store; Config config.Config; Issuer *credentials.Issuer; Revoker *credentials.Revoker; Pools *database.PoolManager }
func (m *Manager) valid(ctx context.Context,p model.Pool)bool{var out map[string]any;return m.Runtime.Run(ctx,&out,"validate-credential","--lease-id",p.LeaseID,"--password-reference",p.PasswordReference)==nil}
func (m *Manager) reconcilePools(ctx context.Context)(int,int,error){
    changes:=0;activeCount:=0;err:=m.Store.WithLock("pools-index",func()error{pools,err:=m.Store.LoadPools();if err!=nil{return err}
        for pod,items:=range pools.Pools{
            sort.Slice(items,func(i,j int)bool{return items[i].Generation>items[j].Generation});wanted:=pools.ActiveByPod[pod];activeIndex:=-1
            for n:=range items{if items[n].Generation==wanted&&items[n].State=="ACTIVE"&&m.valid(ctx,items[n]){activeIndex=n;break}}
            if activeIndex<0{for n:=range items{if (items[n].State=="ACTIVE"||items[n].State=="CANDIDATE")&&m.valid(ctx,items[n]){activeIndex=n;break}}}
            if activeIndex>=0{activeCount++;if pools.ActiveByPod[pod]!=items[activeIndex].Generation{pools.ActiveByPod[pod]=items[activeIndex].Generation;changes++};if items[activeIndex].State!="ACTIVE"{items[activeIndex].State="ACTIVE";changes++}}
            for n:=range items{if n==activeIndex{continue};if items[n].State=="CANDIDATE"{items[n].State="RETIRED";changes++};if items[n].State=="DRAINING"{res,_:=m.Revoker.Revoke(ctx,model.Identity{},items[n].LeaseID,false);if !res.RetryPending&&res.Status=="REVOKED"{items[n].State="RETIRED";changes++}}}
            pools.Pools[pod]=items
        }
        return m.Store.SavePools(pools)});return changes,activeCount,err
}
func (m *Manager) reconcileRequests(ctx context.Context)(int,error){
    if _,err:=m.Store.LoadJournal(m.Config.Failover.JournalTailRecovery);err!=nil{return 0,err};file,err:=m.Store.LoadRequests();if err!=nil{return 0,err};count:=0
    ids:=make([]string,0,len(file.Requests));for id:=range file.Requests{ids=append(ids,id)};sort.Strings(ids)
    for _,id:=range ids{rec:=file.Requests[id];if rec.State=="ACTIVE"&&rec.LeaseID!=""{continue};req:=model.IssueRequest{RequestID:rec.RequestID,PodUID:rec.PodUID,VaultRole:rec.VaultRole,DatabaseRole:rec.DatabaseRole,Generation:1};ident:=model.Identity{PodUID:rec.PodUID,VaultRole:rec.VaultRole,Namespace:"payments",ServiceAccount:"payment-ledger-api"};if _,err:=m.Issuer.Issue(ctx,ident,req);err!=nil{return count,err};count++}
    return count,nil
}
func (m *Manager) Reconcile(ctx context.Context)(Result,error){
    requestChanges,err:=m.reconcileRequests(ctx);if err!=nil{return Result{},err};changes,active,err:=m.reconcilePools(ctx);if err!=nil{return Result{},err};changes+=requestChanges
    cleanup,cleanupErr:=m.Revoker.Cleanup(ctx);for _,r:=range cleanup{if r.Status=="REVOKED"{changes++}}
    var status struct{ActiveNode string `json:"active_node"`;Epoch int `json:"epoch"`;Clock string `json:"clock"`};if err:=m.Runtime.Run(ctx,&status,"status");err!=nil{return Result{},err}
    cp,err:=m.Store.LoadCheckpoint();if err!=nil{return Result{},err};if cp.ActiveNode!=status.ActiveNode||cp.ActiveEpoch!=status.Epoch{changes++};cp.ActiveNode=status.ActiveNode;cp.ActiveEpoch=status.Epoch;cp.LastClock=status.Clock;if !cp.Completed{changes++};cp.Completed=true
    if err:=m.Store.SaveCheckpoint(cp);err!=nil{return Result{},err};return Result{Changes:changes,ActivePools:active,ReconciledRequests:requestChanges,CleanupAttempts:len(cleanup)},cleanupErr
}
EOF

cat > internal/credentials/issuer.go <<'EOF'

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
type runtimeStatus struct { ActiveNode string `json:"active_node"`; Epoch int `json:"epoch"`; Clock string `json:"clock"` }
type recoveredIssue struct { Status string `json:"status"`; model.Lease }
func normalizeLease(l *model.Lease) { if l.DatabaseUsername==""{l.DatabaseUsername=l.Username};if l.Username==""{l.Username=l.DatabaseUsername};if l.Status==""{l.Status="ACTIVE"} }
func (i *Issuer) persistLease(lease model.Lease) error {
    return i.Store.WithLock("leases-index",func() error { f,err:=i.Store.LoadLeases();if err!=nil{return err};f.Leases[lease.LeaseID]=lease;return i.Store.SaveLeases(f) })
}
func (i *Issuer) loadRecord(id string) (model.RequestRecord,bool,error) {
    var rec model.RequestRecord;var ok bool
    err:=i.Store.WithLock("requests-index",func() error { f,err:=i.Store.LoadRequests();if err!=nil{return err};rec,ok=f.Requests[id];return nil });return rec,ok,err
}
func (i *Issuer) saveRecord(rec model.RequestRecord) error {
    return i.Store.WithLock("requests-index",func() error { f,err:=i.Store.LoadRequests();if err!=nil{return err};f.Requests[rec.RequestID]=rec;return i.Store.SaveRequests(f) })
}
func (i *Issuer) currentStatus(ctx context.Context) (runtimeStatus,error) { var out runtimeStatus;err:=i.Runtime.Run(ctx,&out,"status");return out,err }
func (i *Issuer) rememberStatus(ctx context.Context) error { st,err:=i.currentStatus(ctx);if err!=nil{return err};cp,err:=i.Store.LoadCheckpoint();if err!=nil{return err};cp.ActiveNode=st.ActiveNode;cp.ActiveEpoch=st.Epoch;cp.LastClock=st.Clock;return i.Store.SaveCheckpoint(cp) }
func (i *Issuer) adopt(req model.IssueRequest, lease model.Lease, status string) (model.Lease,error) {
    normalizeLease(&lease);if err:=i.persistLease(lease);err!=nil{return model.Lease{},err}
    rec:=model.RequestRecord{RequestID:req.RequestID,Fingerprint:state.Fingerprint(req),PodUID:req.PodUID,VaultRole:req.VaultRole,DatabaseRole:req.DatabaseRole,LeaseID:lease.LeaseID,Username:lease.Username,State:"ACTIVE",UpdatedAt:lease.IssuedAt}
    if err:=i.saveRecord(rec);err!=nil{return model.Lease{},err}
    if err:=i.Store.AppendJournal(map[string]any{"event":status,"request_id":req.RequestID,"lease_id":lease.LeaseID,"username":lease.Username,"generation":lease.Generation,"status":"ACTIVE"});err!=nil{return model.Lease{},err}
    return lease,nil
}
func (i *Issuer) recover(ctx context.Context,req model.IssueRequest) (model.Lease,bool,error) {
    var out recoveredIssue;if err:=i.Runtime.Request(ctx,req,&out,"recover","recover-issue");err!=nil{return model.Lease{},false,err}
    if out.Status=="NONE"{return model.Lease{},false,nil};if err:=i.rememberStatus(ctx);err!=nil{return model.Lease{},false,err};lease,err:=i.adopt(req,out.Lease,out.Status);return lease,true,err
}
func (i *Issuer) Issue(ctx context.Context, ident model.Identity, req model.IssueRequest) (model.Lease,error) {
    if req.RequestID==""||req.PodUID==""{return model.Lease{},fmt.Errorf("INVALID_REQUEST: request_id and pod_uid are required")}
    if req.VaultRole==""{req.VaultRole=ident.VaultRole};if req.DatabaseRole==""{req.DatabaseRole="payment-ledger"};if req.Generation<=0{req.Generation=1}
    if req.VaultRole!=ident.VaultRole||req.DatabaseRole!="payment-ledger"{return model.Lease{},fmt.Errorf("ROLE_DENIED: requested role is not authorized")}
    var result model.Lease
    err:=i.Store.WithLock("request:"+req.RequestID,func() error {
        fp:=state.Fingerprint(req);if rec,ok,err:=i.loadRecord(req.RequestID);err!=nil{return err}else if ok {
            if rec.Fingerprint!=fp{return fmt.Errorf("REQUEST_ID_CONFLICT: request_id was reused with different identity")}
            if rec.LeaseID!="" { var lookup recoveredIssue;if err:=i.Runtime.Run(ctx,&lookup,"lookup-request","--request-id",req.RequestID);err==nil&&lookup.Status=="FOUND"{lease,err:=i.adopt(req,lookup.Lease,"REPLAY_RETURNED");result=lease;return err} }
        }
        if lease,ok,err:=i.recover(ctx,req);err!=nil{return err}else if ok{result=lease;return nil}
        initialStatus,statusErr:=i.currentStatus(ctx);if statusErr!=nil{return statusErr};now:=initialStatus.Clock;rec:=model.RequestRecord{RequestID:req.RequestID,Fingerprint:fp,PodUID:req.PodUID,VaultRole:req.VaultRole,DatabaseRole:req.DatabaseRole,State:"REQUESTED",UpdatedAt:now}
        if err:=i.saveRecord(rec);err!=nil{return err};if err:=i.Store.AppendJournal(map[string]any{"event":"REQUESTED","request_id":req.RequestID,"pod_uid":req.PodUID,"database_role":req.DatabaseRole});err!=nil{return err}
        attempts:=i.Config.Failover.MaximumIssueAttempts;if attempts<=0{attempts=4};var last error
        for n:=0;n<attempts;n++ {
            st,err:=i.currentStatus(ctx);if err!=nil{return err};req.VaultNode=st.ActiveNode;req.VaultEpoch=st.Epoch
            cp,_:=i.Store.LoadCheckpoint();cp.ActiveNode=st.ActiveNode;cp.ActiveEpoch=st.Epoch;cp.LastClock=st.Clock;_ = i.Store.SaveCheckpoint(cp)
            var lease model.Lease;err=i.Runtime.Request(ctx,req,&lease,"issue","issue")
            if err==nil{adopted,aerr:=i.adopt(req,lease,"LEASE_ISSUED");result=adopted;return aerr}
            last=err
            if recovered,ok,rerr:=i.recover(ctx,req);rerr==nil&&ok{result=recovered;return nil}else if rerr!=nil{last=rerr}
            re,ok:=err.(*rt.Error);if !ok||!re.Retryable{break}
        }
        rec.State="FAILED";rec.UpdatedAt=now;_ = i.saveRecord(rec);_ = i.Store.AppendJournal(map[string]any{"event":"FAILED","request_id":req.RequestID,"classification":fmt.Sprint(last)});return last
    })
    return result,err
}
EOF

/usr/local/go/bin/gofmt -w internal/kubernetesauth/login.go internal/credentials/renewal.go internal/credentials/revocation.go internal/database/rotation.go internal/recovery/reconcile.go internal/credentials/issuer.go
/usr/local/go/bin/go test ./...
mkdir -p /app/build
/usr/local/go/bin/go build -o /app/build/lease-agent ./cmd/lease-agent
/usr/local/go/bin/go build -o /app/build/payment-api ./cmd/payment-api
