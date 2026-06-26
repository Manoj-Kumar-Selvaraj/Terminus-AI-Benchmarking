package protocol

import (
    "fmt"
    "vault-dynamic-database-lease-recovery/internal/model"
)
func LeaseResponse(lease model.Lease, version int) (map[string]any,error) {
    username:=lease.Username;if username==""{username=lease.DatabaseUsername}
    switch version {
    case 1:
        return map[string]any{"lease_id":lease.LeaseID,"username":username,"password_reference":lease.PasswordReference,"expires_at":lease.ExpiresAt,"renewable":lease.Renewable},nil
    case 2:
        return map[string]any{"lease_id":lease.LeaseID,"request_id":lease.RequestID,"username":username,"password_reference":lease.PasswordReference,"issued_at":lease.IssuedAt,"expires_at":lease.ExpiresAt,"max_expires_at":lease.MaxExpiresAt,"renewable":lease.Renewable,"generation":lease.Generation,"owner_pod_uid":lease.OwnerPodUID},nil
    default:return nil,fmt.Errorf("UNSUPPORTED_PROTOCOL: protocol version %d is not supported",version)
    }
}
