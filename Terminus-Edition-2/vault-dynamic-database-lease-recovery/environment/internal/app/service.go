package app

import (
    "context"
    "fmt"

    "vault-dynamic-database-lease-recovery/internal/clock"
    "vault-dynamic-database-lease-recovery/internal/config"
    "vault-dynamic-database-lease-recovery/internal/credentials"
    "vault-dynamic-database-lease-recovery/internal/database"
    "vault-dynamic-database-lease-recovery/internal/kubernetesauth"
    "vault-dynamic-database-lease-recovery/internal/model"
    "vault-dynamic-database-lease-recovery/internal/protocol"
    "vault-dynamic-database-lease-recovery/internal/recovery"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
    "vault-dynamic-database-lease-recovery/internal/state"
)

type Service struct { Config config.Config; Runtime *rt.Client; Store *state.Store; Auth *kubernetesauth.Authenticator; Issuer *credentials.Issuer; Renewer *credentials.Renewer; Revoker *credentials.Revoker; Pools *database.PoolManager; Rotator *database.Rotator; Recovery *recovery.Manager }
func New() (*Service,error) {
    cfg,err:=config.Load();if err!=nil{return nil,err};store:=state.New();runtime:=rt.New(store.Dir);clk:=clock.Clock{Runtime:runtime};auth:=&kubernetesauth.Authenticator{Config:cfg.Auth,Runtime:runtime,Clock:clk};issuer:=&credentials.Issuer{Runtime:runtime,Store:store,Config:cfg};renewer:=&credentials.Renewer{Runtime:runtime,Store:store,Config:cfg,Clock:clk,Issuer:issuer};revoker:=&credentials.Revoker{Runtime:runtime,Store:store};pools:=&database.PoolManager{Runtime:runtime,Store:store};rotator:=&database.Rotator{Runtime:runtime,Store:store,Issuer:issuer,Revoker:revoker,Pools:pools};recoveryManager:=&recovery.Manager{Runtime:runtime,Store:store,Config:cfg,Issuer:issuer,Revoker:revoker,Pools:pools}
    return &Service{Config:cfg,Runtime:runtime,Store:store,Auth:auth,Issuer:issuer,Renewer:renewer,Revoker:revoker,Pools:pools,Rotator:rotator,Recovery:recoveryManager},nil
}
func merge(base map[string]any,extra map[string]any)map[string]any{for k,v:=range extra{base[k]=v};return base}
func (s *Service) Login(ctx context.Context,token string)(map[string]any,error){ident,err:=s.Auth.Login(ctx,token);if err!=nil{return nil,err};return map[string]any{"authenticated":true,"namespace":ident.Namespace,"service_account":ident.ServiceAccount,"pod_uid":ident.PodUID,"vault_role":ident.VaultRole,"accessor":ident.Accessor},nil}
func (s *Service) Issue(ctx context.Context,token string,req model.IssueRequest,version int)(map[string]any,error){ident,err:=s.Auth.Login(ctx,token);if err!=nil{return nil,err};if version==0{version=req.ProtocolVersion};if version==0{version=1};lease,err:=s.Issuer.Issue(ctx,ident,req);if err!=nil{return nil,err};if err:=s.Pools.EnsureInitial(ctx,lease,version);err!=nil{return nil,err};resp,err:=protocol.LeaseResponse(lease,version);if err!=nil{return nil,err};return resp,nil}
func (s *Service) Renew(ctx context.Context,token,leaseID string,version int)(map[string]any,error){ident,err:=s.Auth.Login(ctx,token);if err!=nil{return nil,err};if version==0{version=1};result,err:=s.Renewer.Maintain(ctx,ident,leaseID,false);if err!=nil{return nil,err};out:=map[string]any{"action":result.Action,"attempts":result.Attempts,"backoff_seconds":result.BackoffSeconds,"usable":result.Usable,"reason":result.Reason};if result.Lease.LeaseID!=""{leaseResp,e:=protocol.LeaseResponse(result.Lease,version);if e!=nil{return nil,e};merge(out,leaseResp)};return out,nil}
func (s *Service) Rotate(ctx context.Context,token string,req model.IssueRequest,version int)(map[string]any,error){ident,err:=s.Auth.Login(ctx,token);if err!=nil{return nil,err};if version==0{version=req.ProtocolVersion};if version==0{version=1};res,err:=s.Rotator.Rotate(ctx,ident,req,version,false);if err!=nil{return nil,err};return map[string]any{"status":res.Status,"active_generation":res.ActiveGeneration,"new_lease_id":res.NewLeaseID,"old_lease_id":res.OldLeaseID,"cleanup_pending":res.CleanupPending},nil}
func (s *Service) Revoke(ctx context.Context,token,leaseID string)(map[string]any,error){ident,err:=s.Auth.Login(ctx,token);if err!=nil{return nil,err};res,err:=s.Revoker.Revoke(ctx,ident,leaseID,false);if err!=nil{return nil,err};return map[string]any{"lease_id":res.LeaseID,"status":res.Status,"retry_pending":res.RetryPending,"error":res.Error},nil}
func (s *Service) Cleanup(ctx context.Context)(map[string]any,error){results,err:=s.Revoker.Cleanup(ctx);return map[string]any{"results":results,"count":len(results)},err}
func (s *Service) Shutdown(ctx context.Context,token string)(map[string]any,error){ident,err:=s.Auth.Login(ctx,token);if err!=nil{return nil,err};results,err:=s.Revoker.Shutdown(ctx,ident,false);return map[string]any{"results":results,"count":len(results)},err}
func (s *Service) Reconcile(ctx context.Context)(map[string]any,error){res,err:=s.Recovery.Reconcile(ctx);if err!=nil{return nil,err};return map[string]any{"changes":res.Changes,"active_pools":res.ActivePools,"reconciled_requests":res.ReconciledRequests,"cleanup_attempts":res.CleanupAttempts},nil}
var _ = fmt.Sprintf
