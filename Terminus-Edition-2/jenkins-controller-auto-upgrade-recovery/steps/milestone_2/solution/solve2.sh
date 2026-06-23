#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'

import json, shutil
from pathlib import Path
APP=Path('/app')

def load(rel):
    with (APP/rel).open() as f: return json.load(f)

def save(rel,obj):
    p=APP/rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def m1():
    c=load('cluster/controller_deployment.json')
    c['jenkins_version']='2.462.3'
    c['java_major']=17
    c['controller_image']='registry.local/jenkins/controller:2.462.3-jdk17'
    c['cluster']='prod-ci-east'; c['namespace']='jenkins-prod'; c['deployment']='jenkins-controller'; c['service']='jenkins-web'; c['replicas']=1; c['home_claim']='jenkins-home-rwo'; c['home_path']='/app/jenkins_home'
    save('cluster/controller_deployment.json', c)

def m2():
    m1()
    backup=APP/'backups/pre-upgrade-20260618'
    home=APP/'jenkins_home'
    shutil.copy2(backup/'config.xml', home/'config.xml')
    text=(home/'config.xml').read_text().replace('<version>2.426.3</version>','<version>2.462.3</version>')
    (home/'config.xml').write_text(text)
    shutil.copy2(backup/'credentials.xml', home/'credentials.xml')
    shutil.copy2(backup/'queue.xml', home/'queue.xml')
    if (home/'UPGRADE.lock').exists(): (home/'UPGRADE.lock').unlink()
    jobs=load('backups/pre-upgrade-20260618/jobs.json')
    save('jenkins_home/jobs.json', jobs)
    for src in (backup/'jobs').glob('*'):
        dst=home/'jobs'/src.name
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(src,dst)
    state=load('jenkins_home/controller_state.json')
    state.update({'previous_version':'2.426.3','target_version':'2.462.3','home_schema':'recovered-target','upgrade_status':'RESTORED','restored_from_snapshot':'pre-upgrade-20260618'})
    save('jenkins_home/controller_state.json', state)

def m3():
    m2()
    contract=load('config/version_contract.json')
    plugins=load('jenkins_home/plugins/plugins.json')
    for name, req in contract['target_plugin_baseline'].items():
        plugins[name]={'version':req['min_version'],'enabled':True}
    if 'monitoring-theme' not in plugins:
        plugins['monitoring-theme']={'version':'1.0','enabled':True,'optional':True}
    save('jenkins_home/plugins/plugins.json', plugins)

def m4():
    m3()
    p=load('cluster/auto_upgrade_policy.json')
    p.update({'auto_upgrade_enabled':False,'channel':'pinned-lts','source_version':'2.426.3','target_version':'2.462.3','pin_target_version':True,'java_preflight_required':True,'backup_required':True,'required_backup_snapshot':'pre-upgrade-20260618','abort_on_failed_preflight':True,'lock_strategy':'clear-after-verified-restore'})
    save('cluster/auto_upgrade_policy.json', p)

def m5():
    m4()
    topo=load('cluster/topology.json')
    topo['service']={'name':'jenkins-web','routes_to':'jenkins-0'}
    topo['home_claim']={'name':'jenkins-home-rwo','access_mode':'ReadWriteOnce'}
    topo['pods']=[
      {'name':'jenkins-0','role':'active','mounts_home':True,'read_write':True,'elected':True},
      {'name':'jenkins-restore-0','role':'standby','mounts_home':False,'read_write':False,'elected':False}
    ]
    topo['agents']=[{'name':'linux-builder-a','online':True,'remoting_java_major':17},{'name':'linux-builder-b','online':True,'remoting_java_major':17}]
    save('cluster/topology.json', topo)
    q=load('jenkins_home/queue.json')
    seen=set(); items=[]
    for item in q.get('items',[]):
        if item.get('id') not in seen:
            seen.add(item.get('id')); items.append(item)
    byid={i['id']:i for i in items}
    byid.setdefault('q-1001', {'id':'q-1001','job':'payments-ledger/main','cause':'SCM','state':'waiting'})
    byid.setdefault('q-1002', {'id':'q-1002','job':'shared-library/test','cause':'timer','state':'blocked'})
    save('jenkins_home/queue.json', {'items':[byid['q-1001'], byid['q-1002']]})

m2()
PY
