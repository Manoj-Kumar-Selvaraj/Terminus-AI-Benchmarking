# Milestone 4 - Create and run isolated controller jobs

Preserve the recovered Terraform, storage, plugin catalog, and JCasC configuration. Use `/app/scripts/jenkins_fleet_simulator.py` as the offline execution contract, and update `/app/terraform/jenkins_jobs.json` plus `/app/terraform/job_run_trace.json`.

Declare at least six production jobs: at least two assigned to each of `payments-controller`, `risk-controller`, and `platform-controller`. Each job must retain the milestone 3 `controller`, `folder`, and `required_plugins` fields. Controller ownership comes from the job's declared `controller`, not merely from its name. Payments jobs must never run on risk or platform controllers, and the same isolation rule applies to every fleet.

`job_run_trace.json` must contain a `runs` array. Every declared job needs exactly one observable successful run with fields `job`, `controller`, `status: "SUCCESS"`, and a positive integer `build_number`; the controller must equal that job's declared assignment. Do not omit jobs, add undeclared runs, duplicate successful evidence, or use a naming prefix to disguise a cross-controller run. The simulator must exit zero and emit JSON with `ok: true` and all declared job names.
