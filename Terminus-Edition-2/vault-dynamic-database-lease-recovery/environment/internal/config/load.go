package config

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
)

type KubernetesAuth struct {
    Issuer string `json:"issuer"`
    Audience string `json:"audience"`
    Namespace string `json:"namespace"`
    ServiceAccount string `json:"service_account"`
    VaultRole string `json:"vault_role"`
}
type DatabaseRole struct { VaultRole string `json:"vault_role"`; Privileges []string `json:"privileges"`; Tenant string `json:"tenant"` }
type DatabaseRoles struct { Roles map[string]DatabaseRole `json:"roles"` }
type LeasePolicy struct {
    DefaultTTLSeconds int `json:"defaultTtlSeconds"`
    MaxTTLSeconds int `json:"maxTtlSeconds"`
    RenewalWindowSeconds int `json:"renewalWindowSeconds"`
    MinimumRenewalIntervalSeconds int `json:"minimumRenewalIntervalSeconds"`
    MaxRenewalAttempts int `json:"maxRenewalAttempts"`
    RetryBackoffSeconds []int `json:"retryBackoffSeconds"`
}
type PoolPolicy struct { ValidationOperation string `json:"validationOperation"`; DrainGraceSeconds int `json:"drainGraceSeconds"`; MaximumRetiredPools int `json:"maximumRetiredPools"`; EmergencyStaticCredentialReference string `json:"emergencyStaticCredentialReference"` }
type FailoverPolicy struct { Nodes []string `json:"nodes"`; MaximumIssueAttempts int `json:"maximumIssueAttempts"`; RequestLockTimeoutSeconds int `json:"requestLockTimeoutSeconds"`; JournalTailRecovery bool `json:"journalTailRecovery"` }
type Config struct { Auth KubernetesAuth; Roles DatabaseRoles; Lease LeasePolicy; Pool PoolPolicy; Failover FailoverPolicy }

func read(name string, out any) error {
    dir:=os.Getenv("LEASE_AGENT_CONFIG_DIR"); if dir=="" { dir="/app/config" }
    raw,err:=os.ReadFile(filepath.Join(dir,name)); if err!=nil{return err}
    if err:=json.Unmarshal(raw,out); err!=nil{return fmt.Errorf("parse %s: %w",name,err)}
    return nil
}
func Load() (Config,error) {
    var c Config
    if err:=read("kubernetes-auth.json",&c.Auth);err!=nil{return c,err}
    if err:=read("database-roles.json",&c.Roles);err!=nil{return c,err}
    if err:=read("lease-policy.json",&c.Lease);err!=nil{return c,err}
    if err:=read("connection-pool.json",&c.Pool);err!=nil{return c,err}
    if err:=read("failover-policy.json",&c.Failover);err!=nil{return c,err}
    if c.Lease.DefaultTTLSeconds<=0||c.Lease.MaxTTLSeconds<c.Lease.DefaultTTLSeconds||c.Lease.RenewalWindowSeconds<=0{return c,fmt.Errorf("invalid lease policy")}
    if len(c.Failover.Nodes)<2{return c,fmt.Errorf("at least two failover nodes are required")}
    return c,nil
}
