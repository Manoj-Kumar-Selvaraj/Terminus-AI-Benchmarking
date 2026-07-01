The platform team is preparing a credentialless Windows Server to Amazon Linux EC2 cutover plan. Build the Terraform module under `/app/environment/terraform/modules/ec2_linux_migration` and wire it through the existing root module so the normal operator command, `/app/environment/scripts/render-migration-plan`, produces `/app/output/ec2_linux_migration_plan.json` from Terraform rather than from handwritten JSON.

Use `/app/environment/terraform/docs/migration_contract.md` and `/app/environment/terraform/migration.auto.tfvars.json` as the source of truth for the inventory, disk mapping, tags, security defaults, outputs, and plan JSON expectations. The Terraform workspace is offline-only: do not call live AWS APIs, add Terraform data sources, apply changes, or create one-off EC2 resources outside the migration module.

Before finishing, run `terraform fmt -recursive` on `/app/environment/terraform` so every file passes `terraform fmt -check -recursive`. The verifier runs that formatting gate before it evaluates the plan JSON.

The final plan should create one private Amazon Linux replacement instance for each legacy Windows workload, restore every documented data snapshot as encrypted gp3 storage, attach those volumes with safe Linux device names, and preserve traceability back to the source Windows instances. Each instance `root_block_device` must include a `tags` block with `VolumeRole = "root"` (alongside the workload identity tags on the root gp3 disk) so the plan JSON exposes that tag in `resource_changes[*].change.after.root_block_device`.

Instances must be SSM-managed, private-only, IMDSv2-hardened, termination-protected, monitored, EBS-optimized, and free of legacy RDP, WinRM, and domain-join administration groups.

Keep both root outputs populated from the module: `planned_linux_instances` keyed by workload and `planned_data_volumes` keyed by workload plus Linux device name. Run the render script to regenerate the plan JSON. The generated plan must include exactly four Linux instances, five restored data volumes, five non-force-detach attachments, no Terraform data-mode entries, no public IPs, and no static-output shortcut.
