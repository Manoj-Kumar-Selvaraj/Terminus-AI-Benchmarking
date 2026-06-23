#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
ACTIVE_LOCK_ENFORCEMENT = True
SERIAL_GUARDS = True
CHECKPOINT_RESUME = True
WORKSPACE_PROVIDER_ISOLATION = False
DRIFT_GUARDS = False
class ApplyError(Exception): pass

def load(path, default):
    if not Path(path).exists(): return default
    return json.loads(Path(path).read_text())
def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True)+"\n")
def audit(out, rec):
    p=Path(out)/'lock_audit.jsonl'; p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a') as f: f.write(json.dumps(rec, sort_keys=True)+"\n")
def ensure_ws(state, ws):
    state.setdefault('workspaces',{}).setdefault(ws, {'resources':{}, 'outputs':{}})
def now(): return 1000

def acquire(lock, ws, holder, serial, lineage):
    active=lock.get('active')
    if ACTIVE_LOCK_ENFORCEMENT and active and active.get('workspace')==ws and active.get('holder')!=holder and active.get('expires_at',0)>now():
        raise ApplyError('active lock held by '+active.get('holder','unknown'))
    lock['active']={'workspace':ws,'holder':holder,'state_serial':serial,'lineage':lineage,'expires_at':now()+300}

def release(lock, holder):
    if lock.get('active',{}).get('holder')==holder: lock.pop('active',None)

def apply_action(ws_state, action):
    res=ws_state.setdefault('resources',{})
    op=action.get('op','set'); name=action['name']
    if op=='delete': res.pop(name, None)
    else: res[name]=action.get('value')

def run_apply(args):
    state=load(args.state, {'lineage':'L1','serial':0,'workspaces':{}})
    lock=load(args.lock, {})
    plan=load(args.plan, {})
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)
    ws=args.workspace or plan.get('workspace','default'); holder=args.run_id or plan.get('run_id','agent')
    try:
        ensure_ws(state, ws)
        acquire(lock, ws, holder, state.get('serial',0), state.get('lineage',''))
        if SERIAL_GUARDS:
            if plan.get('lineage') != state.get('lineage') or int(plan.get('serial',-1)) != int(state.get('serial',-2)):
                raise ApplyError('saved plan is stale for current state serial/lineage')
        if DRIFT_GUARDS:
            required=plan.get('provider_hash')
            lockfile=load(Path(args.lock_file), {}) if args.lock_file else {}
            if required and lockfile.get('provider_hash') != required:
                raise ApplyError('provider lock hash mismatch')
            cache=load(Path(args.provider_cache), {'providers':[]}) if args.provider_cache else {'providers':[]}
            if required and required not in cache.get('providers',[]):
                raise ApplyError('provider mirror missing required hash')
        cp_path=Path(args.checkpoint) if args.checkpoint else Path(args.state).with_suffix('.checkpoint.json')
        applied_names=[]
        cp=load(cp_path, {'workspace':ws,'run_id':holder,'applied':[]}) if CHECKPOINT_RESUME else {'applied':[]}
        if CHECKPOINT_RESUME and cp.get('run_id') not in {holder, None} and cp.get('applied'):
            raise ApplyError('checkpoint belongs to another run')
        for idx, action in enumerate(plan.get('actions',[]),1):
            key=f"{idx}:{action['name']}"
            if CHECKPOINT_RESUME and key in cp.get('applied',[]):
                continue
            apply_action(state['workspaces'][ws], action)
            applied_names.append(action['name'])
            if CHECKPOINT_RESUME:
                cp.setdefault('applied',[]).append(key); cp['workspace']=ws; cp['run_id']=holder; save(cp_path, cp)
            if args.crash_after and idx>=args.crash_after:
                save(args.state, state); save(args.lock, lock); save(out/'apply_result.json', {'status':'CRASHED','applied':applied_names})
                return 66
        state['serial']=int(state.get('serial',0))+1
        if WORKSPACE_PROVIDER_ISOLATION:
            state.setdefault('backend_keys',{})[ws]=plan.get('backend_key', ws)
        save(args.state, state); release(lock, holder); save(args.lock, lock)
        if CHECKPOINT_RESUME and cp_path.exists(): cp_path.unlink()
        save(out/'apply_result.json', {'status':'APPLIED','workspace':ws,'serial':state['serial'],'applied':applied_names})
        audit(out, {'event':'apply','workspace':ws,'holder':holder,'serial':state['serial']})
        return 0
    except Exception as exc:
        if ACTIVE_LOCK_ENFORCEMENT: save(args.lock, lock)
        save(out/'apply_result.json', {'status':'FAILED_CLOSED','error':str(exc),'workspace':ws})
        audit(out, {'event':'reject','workspace':ws,'holder':holder,'error':str(exc)})
        return 2

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd', required=True)
    a=sub.add_parser('apply'); a.add_argument('--state',required=True); a.add_argument('--lock',required=True); a.add_argument('--plan',required=True); a.add_argument('--out',required=True); a.add_argument('--workspace',default=''); a.add_argument('--run-id',default=''); a.add_argument('--crash-after',type=int,default=0); a.add_argument('--checkpoint',default=''); a.add_argument('--lock-file',default=''); a.add_argument('--provider-cache',default='')
    ns=p.parse_args(); raise SystemExit(run_apply(ns))
if __name__=='__main__': main()
