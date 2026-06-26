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

/usr/local/go/bin/gofmt -w internal/kubernetesauth/login.go internal/credentials/renewal.go
/usr/local/go/bin/go test ./...
mkdir -p /app/build
/usr/local/go/bin/go build -o /app/build/lease-agent ./cmd/lease-agent
/usr/local/go/bin/go build -o /app/build/payment-api ./cmd/payment-api
