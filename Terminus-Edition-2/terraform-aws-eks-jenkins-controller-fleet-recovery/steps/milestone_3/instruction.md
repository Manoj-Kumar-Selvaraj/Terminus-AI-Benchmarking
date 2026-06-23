# Milestone 3 — Pin plugins and JCasC controller bootstrap

Controller boot still fails because required plugins and bootstrap policy are incomplete. Update `/app/terraform/plugin-catalog.yaml`, `/app/terraform/jcasc.yaml`, and `/app/terraform/jenkins_jobs.json`.

## Plugin catalog

Set `pluginSource: internal-mirror` and pin all eight approved plugin IDs from `/app/docs/jenkins_fleet_contract.md`:

- configuration-as-code
- kubernetes
- workflow-aggregator
- job-dsl
- git
- credentials
- matrix-auth
- cloudbees-casc-client

Do not use `latest` or `updates.jenkins.io`.

## JCasC and jobs schema

`jenkins_jobs.json` must have this shape:

```json
{
  "controllers": {
    "payments-controller": {"seed_job": "...", "jobs": ["..."]},
    "risk-controller": {"seed_job": "...", "jobs": ["..."]},
    "platform-controller": {"seed_job": "...", "jobs": ["..."]}
  },
  "jobs": {
    "job-name": {"controller": "payments-controller", "folder": "...", "required_plugins": ["..."]}
  }
}
```

JCasC must preserve restricted authorization (`matrix` or `roleBased`) and set `allowsSignup: false`. Each controller needs a seed job; JOC must not directly own production jobs.

Every entry in the `jobs` object must have a nonblank `controller`, a nonblank `folder`, and a nonempty `required_plugins` array. Every listed plugin must be one of the eight pinned catalog IDs.
