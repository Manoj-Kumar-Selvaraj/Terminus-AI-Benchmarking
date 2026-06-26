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

/usr/local/go/bin/gofmt -w internal/kubernetesauth/login.go
/usr/local/go/bin/go test ./...
mkdir -p /app/build
/usr/local/go/bin/go build -o /app/build/lease-agent ./cmd/lease-agent
/usr/local/go/bin/go build -o /app/build/payment-api ./cmd/payment-api
