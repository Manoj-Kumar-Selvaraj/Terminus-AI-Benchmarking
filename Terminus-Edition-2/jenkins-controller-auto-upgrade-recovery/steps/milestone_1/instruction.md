# M1 — Recover controller runtime compatibility after auto-upgrade

The Jenkins controller in `prod-ci-east` was auto-upgraded from the previously healthy release to the selected target release. The cluster deployment now advertises the target controller image, but the controller fails before it reaches Jenkins initialization.

Evidence is available in:

- `/app/evidence/auto_upgrade_event.log`
- `/app/evidence/controller_crashloop.log`
- `/app/docs/jenkins_upgrade_contract.md`
- `/app/cluster/controller_deployment.json`
- `/app/config/version_contract.json`


## Shared constraints

- Work under `/app`.
- Use `/app/scripts/run_controller.sh` or `python3 /app/scripts/jenkins_cluster_sim.py diagnose --json` to exercise the offline simulator.
- Do not require a real Jenkins controller, Kubernetes cluster, network access, Jenkins CLI, or cloud credentials.
- Preserve the cluster identity: `prod-ci-east`, namespace `jenkins-prod`, deployment `jenkins-controller`, service `jenkins-web`, and PVC claim `jenkins-home-rwo`.
- Preserve `/app/jenkins_home`; do not replace it with a tiny fake home or delete jobs/credentials.
- Preserve the target Jenkins version `2.462.3` from the incident contract.
- Do not edit tests or simulator output files as a substitute for restoring the simulated system state.


## Input format

`/app/cluster/controller_deployment.json` is JSON with these required fields:

```json
{
  "cluster": "prod-ci-east",
  "namespace": "jenkins-prod",
  "deployment": "jenkins-controller",
  "service": "jenkins-web",
  "replicas": 1,
  "jenkins_version": "2.462.3",
  "controller_image": "...",
  "java_major": 11,
  "home_claim": "jenkins-home-rwo",
  "home_path": "/app/jenkins_home"
}
```

`/app/config/version_contract.json` defines the simulator's version-to-Java compatibility contract.

## Expected result

After M1, diagnostics must no longer stop at phase `RUNTIME_INCOMPATIBLE`. Later phases may still fail.

## Requirements tested in M1

1. The target Jenkins version remains `2.462.3`.
2. The configured Java major version satisfies the target version contract.
3. The controller image metadata is consistent with the required Java runtime.
4. The deployment keeps the original cluster, namespace, deployment, service, replica count, and home claim identity.
5. The recovery does not bypass the simulator by writing `/app/out/controller_status.json` directly.
6. The diagnostic phase progresses beyond runtime incompatibility while still exposing later incident damage.
