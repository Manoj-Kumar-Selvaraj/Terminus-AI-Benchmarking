#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
IMMUTABLE_IMAGE_IDENTITY = True
ROUTE_HEALTH_GATE = True
DEPLOY_HISTORY_IDEMPOTENCY = True
CERTIFICATE_SNI_VALIDATION = False
ROLLBACK_WITHOUT_REBUILD = False
class DeployError(Exception): pass

def load(path, default):
    p=Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text())
def save(path,obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True)+"\n")
def write_result(out,obj): save(Path(out)/'deploy_result.json', obj)
def image_id(m): return m.get('digest') if IMMUTABLE_IMAGE_IDENTITY else m.get('tag')
def health_ok(m):
    routes=m.get('routes',[]); checks=m.get('health',{})
    return all(checks.get(r)=="ok" for r in routes)
def cert_ok(m):
    cert=m.get('cert',{})
    return bool(cert.get('version')) and cert.get('sni')==m.get('edge_host') and cert.get('valid') is not False

def deploy(args):
    state=load(args.state, {'active':None,'previous':None,'containers':[],'cert_history':[],'connections':0})
    m=load(args.manifest,{})
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    try:
        if args.command=='rollback':
            if not ROLLBACK_WITHOUT_REBUILD: raise DeployError('rollback rebuild path is disabled')
            prev=state.get('previous')
            if not prev: raise DeployError('no immutable previous release')
            state['connections']=0; state['active']=prev; state['previous']=None
            state['containers']=[c for c in state.get('containers',[]) if c.get('digest')==prev.get('digest') and c.get('port')==443]
            if not state['containers']: state['containers'].append({'name':'edge-proxy','digest':prev.get('digest'),'port':443,'status':'running'})
            save(args.state,state); write_result(out,{'status':'ROLLED_BACK','active':state['active']}); return 0
        if ROUTE_HEALTH_GATE and not health_ok(m): raise DeployError('route health check failed')
        if CERTIFICATE_SNI_VALIDATION and not cert_ok(m): raise DeployError('certificate bundle invalid for edge host')
        digest=image_id(m)
        if not digest: raise DeployError('missing promoted image identity')
        if DEPLOY_HISTORY_IDEMPOTENCY:
            state['containers']=[c for c in state.get('containers',[]) if not (c.get('port')==443 and c.get('status')!='running')]
            running=[c for c in state.get('containers',[]) if c.get('port')==443 and c.get('status')=='running']
            if len(running)>1: raise DeployError('ambiguous active proxy containers')
            if running and running[0].get('digest')==digest and state.get('active',{}).get('config_sha')==m.get('config_sha'):
                write_result(out,{'status':'NOOP','active':state.get('active')}); save(args.state,state); return 0
        active={'release_id':m.get('release_id'), 'digest':digest, 'tag':m.get('tag'), 'config_sha':m.get('config_sha'), 'cert_version':m.get('cert',{}).get('version'), 'routes':m.get('routes',[])}
        if state.get('active') and state.get('active') != active:
            state['previous']=state['active']
        if CERTIFICATE_SNI_VALIDATION: state.setdefault('cert_history',[]).append(active['cert_version'])
        state['active']=active
        state['containers']=[c for c in state.get('containers',[]) if c.get('port')!=443]
        state['containers'].append({'name':'edge-proxy','digest':digest,'port':443,'status':'running'})
        save(args.state,state); write_result(out,{'status':'PROMOTED','active':active,'container_count':len(state['containers'])}); return 0
    except Exception as exc:
        write_result(out,{'status':'FAILED_CLOSED','error':str(exc),'active':state.get('active')}); save(args.state,state); return 2

def main():
    p=argparse.ArgumentParser(); p.add_argument('command', choices=['deploy','rollback']); p.add_argument('--manifest', required=True); p.add_argument('--state', required=True); p.add_argument('--out', required=True)
    raise SystemExit(deploy(p.parse_args()))
if __name__=='__main__': main()
