package model

import "encoding/json"

type Claims struct {
    Issuer         string          `json:"iss"`
    Subject        string          `json:"sub"`
    Audience       json.RawMessage `json:"aud"`
    Namespace      string          `json:"namespace"`
    ServiceAccount string          `json:"service_account"`
    PodUID         string          `json:"pod_uid"`
    Expires        int64           `json:"exp"`
    NotBefore      int64           `json:"nbf"`
    IssuedAt       int64           `json:"iat"`
}

type Identity struct {
    Namespace      string `json:"namespace"`
    ServiceAccount string `json:"service_account"`
    PodUID         string `json:"pod_uid"`
    VaultRole      string `json:"vault_role"`
    Accessor       string `json:"accessor"`
}

type IssueRequest struct {
    RequestID      string `json:"request_id"`
    PodUID         string `json:"pod_uid"`
    VaultRole      string `json:"vault_role"`
    DatabaseRole   string `json:"database_role"`
    RequestedAt    string `json:"requested_at"`
    ProtocolVersion int   `json:"protocol_version"`
    Generation     int    `json:"generation,omitempty"`
    VaultNode      string `json:"vault_node,omitempty"`
    VaultEpoch     int    `json:"vault_epoch,omitempty"`
}

type Lease struct {
    LeaseID           string `json:"lease_id"`
    RequestID         string `json:"request_id"`
    DatabaseUsername  string `json:"database_username"`
    Username          string `json:"username,omitempty"`
    PasswordReference string `json:"password_reference"`
    IssuedAt          string `json:"issued_at"`
    ExpiresAt         string `json:"expires_at"`
    Renewable         bool   `json:"renewable"`
    MaxExpiresAt      string `json:"max_expires_at"`
    Generation        int    `json:"generation"`
    VaultNode         string `json:"vault_node"`
    VaultEpoch        int    `json:"vault_epoch"`
    Status            string `json:"status"`
    OwnerPodUID       string `json:"owner_pod_uid"`
    LastRenewedAt     string `json:"last_renewed_at,omitempty"`
}

type Pool struct {
    PodUID            string `json:"pod_uid"`
    Generation        int    `json:"generation"`
    LeaseID           string `json:"lease_id"`
    Username          string `json:"username"`
    PasswordReference string `json:"password_reference"`
    State             string `json:"state"`
    CreatedAt         string `json:"created_at"`
    DrainDeadline     string `json:"drain_deadline,omitempty"`
    ProtocolVersion   int    `json:"protocol_version"`
}

type PoolFile struct {
    ActiveByPod map[string]int    `json:"active_by_pod"`
    Pools       map[string][]Pool `json:"pools"`
}

type LeaseFile struct { Leases map[string]Lease `json:"leases"` }

type RequestRecord struct {
    RequestID    string `json:"request_id"`
    Fingerprint  string `json:"fingerprint"`
    PodUID       string `json:"pod_uid"`
    VaultRole    string `json:"vault_role"`
    DatabaseRole string `json:"database_role"`
    LeaseID      string `json:"lease_id,omitempty"`
    Username     string `json:"username,omitempty"`
    State        string `json:"state"`
    UpdatedAt    string `json:"updated_at"`
}

type RequestFile struct { Requests map[string]RequestRecord `json:"requests"` }

type Checkpoint struct {
    LastClock       string `json:"last_clock"`
    LastReconcileID string `json:"last_reconcile_id"`
    Completed       bool   `json:"completed"`
    ActiveNode      string `json:"active_node,omitempty"`
    ActiveEpoch     int    `json:"active_epoch,omitempty"`
}
