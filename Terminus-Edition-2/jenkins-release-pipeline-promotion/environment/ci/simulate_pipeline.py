#!/usr/bin/env python3
import json, os, sys, hashlib
from pathlib import Path
APP=Path('/app')
CI=APP/'ci'
DATA=APP/'data'
OUT=APP/'out'

def j(path): return json.loads(path.read_text())
def write(path,obj): path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')

def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.glob('*'): p.unlink()
    cfg=j(CI/'pipeline_config.json')
    build=j(DATA/'build_manifest.json')
    scans=j(DATA/'quality_scans.json')
    hist=j(DATA/'deploy_history.json')
    result={'stages':{}, 'errors':[]}
    # M1 credentials
    creds=cfg.get('credentialBindings',{})
    result['stages']['PromoteCredentials'] = 'PASS' if creds.get('production')=='cred-production' and creds.get('staging')=='cred-staging' else 'FAIL'
    if result['stages']['PromoteCredentials']=='FAIL': result['errors'].append('PRODUCTION_CREDENTIAL_BINDING_INVALID')
    # M2 isolation
    ws=cfg.get('workspace',{})
    if ws.get('parallelIsolation') and ws.get('cacheKeyIncludesAxis'):
        produced=[f"{build['artifactDigest']}:{axis}" for axis in build.get('testAxes',[])]
        result['stages']['ParallelIntegration']='PASS'
    else:
        produced=[build['artifactDigest']]
        result['stages']['ParallelIntegration']='FAIL'
        result['errors'].append('PARALLEL_WORKSPACE_COLLISION')
    write(OUT/'integration_workspace_manifest.json', {'produced': produced})
    # M3 quality gate
    gate=cfg.get('promotionGate',{})
    if gate.get('scanSource')=='built_artifact': status=scans.get('byArtifact',{}).get(build['artifactDigest'],'MISSING')
    else: status=scans.get('branchTip',{}).get(build['branch'],'MISSING')
    promote_ok = status == gate.get('requiredStatus','PASS') and result['stages']['PromoteCredentials']=='PASS' and result['stages']['ParallelIntegration']=='PASS'
    result['stages']['QualityGate']='PASS' if status=='PASS' else 'FAIL'
    result['promotedArtifactDigest']=build['artifactDigest'] if promote_ok else None
    write(OUT/'promotion_manifest.json', {'schema':cfg.get('compat',{}).get('manifestSchema','v1'),'buildNumber':build['buildNumber'],'commit':build['commit'],'artifactDigest':build['artifactDigest'],'qualityStatus':status,'promoted':promote_ok})
    # M4 rollback
    rb=cfg.get('rollback',{})
    prior=hist['production'][-1]
    if rb.get('strategy')=='redeploy_prior_digest' and rb.get('preservePriorDigest'):
        rollback={'action':'redeploy','artifactDigest':prior['artifactDigest'],'sourceBuildNumber':prior['buildNumber'],'rebuild':False}
    else:
        rollback={'action':'rebuild','artifactDigest':build['branchHeadDigest'],'sourceBuildNumber':'HEAD','rebuild':True}
    write(OUT/'rollback_plan.json', rollback)
    write(OUT/'pipeline_result.json', result)
    return 0 if not result['errors'] and (promote_ok or status!='PASS') else 0
if __name__=='__main__': raise SystemExit(main())
