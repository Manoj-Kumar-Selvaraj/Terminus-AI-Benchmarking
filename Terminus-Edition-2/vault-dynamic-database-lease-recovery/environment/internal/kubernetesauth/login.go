package kubernetesauth

import (
    "context"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "os"
    "strings"

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
func (a *Authenticator) Login(ctx context.Context, tokenPath string) (model.Identity,error) {
    raw,err:=os.ReadFile(tokenPath);if err!=nil{return model.Identity{},&AuthError{Code:"EMPTY_TOKEN",Message:"cannot read token"}}
    token:=strings.TrimSpace(string(raw));logging.Event("login_attempt",map[string]any{"raw_jwt":token})
    if token==""{return model.Identity{},&AuthError{Code:"EMPTY_TOKEN",Message:"empty token"}}
    var checked validation;if err:=a.Runtime.Run(ctx,&checked,"validate-token","--token-file",tokenPath);err!=nil{return model.Identity{},err}
    var claims model.Claims;if err:=json.Unmarshal(checked.Claims,&claims);err!=nil{return model.Identity{},err}
    if !strings.HasPrefix(claims.Subject,"system:serviceaccount:"+a.Config.Namespace+":"+a.Config.ServiceAccount){return model.Identity{},&AuthError{Code:"WRONG_SERVICE_ACCOUNT",Message:"subject denied"}}
    if claims.ServiceAccount==""{claims.ServiceAccount=a.Config.ServiceAccount};if claims.Namespace==""{claims.Namespace=a.Config.Namespace}
    sum:=sha256.Sum256([]byte(token));return model.Identity{Namespace:claims.Namespace,ServiceAccount:claims.ServiceAccount,PodUID:claims.PodUID,VaultRole:a.Config.VaultRole,Accessor:hex.EncodeToString(sum[:12])},nil
}
