# Jenkins upgrade contract for this task

This is a simulator contract, not a live Jenkins compatibility matrix.

The production cluster had Jenkins `2.426.3` running with Java `11`. The auto-upgrade selected Jenkins `2.462.3`. In this task's offline contract, Jenkins `2.462.3` requires Java `17`.

Public contracts that must be preserved:

- cluster name: `prod-ci-east`
- namespace: `jenkins-prod`
- deployment name: `jenkins-controller`
- service name: `jenkins-web`
- persistent home claim: `jenkins-home-rwo`
- target Jenkins version: `2.462.3`
- Jenkins home path: `/app/jenkins_home`
- simulator entrypoint: `/app/scripts/jenkins_cluster_sim.py`

The target version must not be silently downgraded to make the simulator pass. Safe rollback evidence may be documented, but milestone success requires the recovered target controller to be compatible with the target runtime contract.
