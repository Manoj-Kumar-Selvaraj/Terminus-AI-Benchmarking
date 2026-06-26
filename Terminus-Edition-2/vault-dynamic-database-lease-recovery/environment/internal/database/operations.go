package database

import (
    "context"
    "fmt"

    rt "vault-dynamic-database-lease-recovery/internal/runtime"
)

type OperationRequest struct { PodUID string `json:"pod_uid"`; Generation int `json:"generation,omitempty"`; Operation string `json:"operation"`; Tenant string `json:"tenant"` }
type SessionExecRequest struct { SessionID string `json:"session_id"`; Operation string `json:"operation"`; Tenant string `json:"tenant"` }
type API struct { Runtime *rt.Client; Pools *PoolManager }
func (a *API) operationPayload(req OperationRequest)(map[string]any,error){
    if req.PodUID==""||req.Operation==""||req.Tenant==""{return nil,fmt.Errorf("INVALID_REQUEST: pod_uid, operation, and tenant are required")}
    pool,err:=a.Pools.Active(req.PodUID);if err!=nil{return nil,err};if req.Generation!=0&&req.Generation!=pool.Generation{return nil,fmt.Errorf("STALE_POOL_GENERATION: requested pool is not active")}
    return map[string]any{"lease_id":pool.LeaseID,"username":pool.Username,"password_reference":pool.PasswordReference,"operation":req.Operation,"tenant":req.Tenant},nil
}
func (a *API) Run(ctx context.Context,req OperationRequest)(map[string]any,error){payload,err:=a.operationPayload(req);if err!=nil{return nil,err};var out map[string]any;err=a.Runtime.Request(ctx,payload,&out,"dbop","run-db-operation");return out,err}
func (a *API) SessionOpen(ctx context.Context,req OperationRequest)(map[string]any,error){payload,err:=a.operationPayload(req);if err!=nil{return nil,err};var out map[string]any;err=a.Runtime.Request(ctx,payload,&out,"session","session-open");return out,err}
func (a *API) SessionExec(ctx context.Context,req SessionExecRequest)(map[string]any,error){if req.SessionID==""{return nil,fmt.Errorf("INVALID_REQUEST: session_id is required")};var out map[string]any;err:=a.Runtime.Request(ctx,map[string]any{"session_id":req.SessionID,"operation":req.Operation,"tenant":req.Tenant},&out,"session-exec","session-exec");return out,err}
func (a *API) SessionClose(ctx context.Context,id string)(map[string]any,error){var out map[string]any;err:=a.Runtime.Run(ctx,&out,"session-close","--session-id",id);return out,err}
