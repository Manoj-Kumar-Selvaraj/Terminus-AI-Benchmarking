#!/usr/bin/env bash
set -euo pipefail

module_dir="/app/environment/terraform/modules/ec2_linux_migration"
rm -rf "${module_dir}"
mkdir -p "${module_dir}"
mkdir -p "${module_dir}/cloud-init"

cat > "${module_dir}/variables.tf" <<'HCL'
variable "region" {
  description = "AWS region used only for offline provider planning."
  type        = string
}

variable "common_tags" {
  description = "Common tags inherited from the migration root module."
  type        = map(string)
}

variable "migration_defaults" {
  description = "Shared EC2 hardening and storage defaults."
  type        = any
}

variable "legacy_windows_instances" {
  description = "Legacy Windows EC2 inventory to replace with Linux instances."
  type        = any
}
HCL

cat > "${module_dir}/main.tf" <<'HCL'
locals {
  base_resource_tags = merge(var.common_tags, {
    CutoverId      = var.migration_defaults.cutover_id
    MigrationWave  = var.migration_defaults.migration_wave
    MigratedFromOS = "windows"
    OSFamily       = "linux"
  })

  linux_instances = {
    for workload, cfg in var.legacy_windows_instances : workload => cfg
  }

  instance_tags = {
    for workload, cfg in local.linux_instances : workload => merge(local.base_resource_tags, {
      Name             = "${cfg.workload}-linux"
      LegacyInstanceId = cfg.legacy_instance_id
      Workload         = cfg.workload
      Application      = cfg.application
      Environment      = cfg.environment
      Owner            = cfg.owner
      OwnerCostCenter  = cfg.cost_center
      PatchGroup       = cfg.patch_group
      BackupTier       = cfg.backup_tier
    })
  }

  data_volume_maps = [
    for workload, cfg in local.linux_instances : {
      for volume in cfg.data_volumes : "${workload}:${volume.device_name}" => {
        workload           = workload
        legacy_instance_id = cfg.legacy_instance_id
        application        = cfg.application
        environment        = cfg.environment
        owner              = cfg.owner
        cost_center        = cfg.cost_center
        patch_group        = cfg.patch_group
        backup_tier        = cfg.backup_tier
        availability_zone  = cfg.availability_zone
        device_name        = volume.device_name
        snapshot_id        = volume.snapshot_id
        size_gib           = volume.size_gib
        volume_role        = volume.volume_role
        iops               = volume.iops
        throughput         = volume.throughput
      }
    }
  ]

  data_volumes = merge(local.data_volume_maps...)
}

resource "aws_ebs_volume" "data" {
  for_each = local.data_volumes

  availability_zone = each.value.availability_zone
  snapshot_id       = each.value.snapshot_id
  size              = each.value.size_gib
  type              = "gp3"
  encrypted         = true
  kms_key_id        = var.migration_defaults.kms_key_id
  iops              = each.value.iops
  throughput        = each.value.throughput

  tags = merge(local.base_resource_tags, {
    Name             = "${each.value.workload}-linux-${each.value.volume_role}"
    LegacyInstanceId = each.value.legacy_instance_id
    Workload         = each.value.workload
    Application      = each.value.application
    Environment      = each.value.environment
    Owner            = each.value.owner
    OwnerCostCenter  = each.value.cost_center
    PatchGroup       = each.value.patch_group
    BackupTier       = each.value.backup_tier
    DeviceName       = each.value.device_name
    SourceSnapshot   = each.value.snapshot_id
    VolumeRole       = each.value.volume_role
  })
}

resource "aws_volume_attachment" "data" {
  for_each = local.data_volumes

  device_name  = each.value.device_name
  volume_id    = aws_ebs_volume.data[each.key].id
  instance_id  = aws_instance.linux[each.value.workload].id
  force_detach = false
}

resource "aws_instance" "linux" {
  for_each = local.linux_instances

  ami                         = each.value.target_ami_id
  instance_type               = each.value.instance_type
  availability_zone           = each.value.availability_zone
  subnet_id                   = each.value.subnet_id
  private_ip                  = each.value.private_ip
  associate_public_ip_address = false
  vpc_security_group_ids = sort(tolist(setunion(
    setsubtract(toset(each.value.security_group_ids), toset(var.migration_defaults.forbidden_admin_groups)),
    toset([var.migration_defaults.required_ssm_security_group])
  )))
  iam_instance_profile        = var.migration_defaults.iam_instance_profile
  disable_api_termination     = var.migration_defaults.disable_api_termination
  monitoring                  = var.migration_defaults.detailed_monitoring
  ebs_optimized               = var.migration_defaults.ebs_optimized
  user_data_replace_on_change = true
  user_data_base64 = base64encode(templatefile("${path.module}/cloud-init/linux-bootstrap.sh.tftpl", {
    workload       = each.value.workload
    environment    = each.value.environment
    application    = each.value.application
    cutover_id     = var.migration_defaults.cutover_id
    migration_wave = var.migration_defaults.migration_wave
  }))

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = var.migration_defaults.metadata_http_tokens
    http_put_response_hop_limit = var.migration_defaults.metadata_hop_limit
    instance_metadata_tags      = var.migration_defaults.metadata_instance_tags
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = each.value.root_gib
    encrypted   = true
    kms_key_id  = var.migration_defaults.kms_key_id
    tags = merge(local.instance_tags[each.key], {
      Name       = "${each.value.workload}-linux-root"
      VolumeRole = "root"
    })
  }

  tags = local.instance_tags[each.key]
}
HCL

cat > "${module_dir}/outputs.tf" <<'HCL'
output "planned_linux_instances" {
  description = "Linux replacement instance plan keyed by workload."
  value = {
    for workload, cfg in local.linux_instances : workload => {
      ami                = cfg.target_ami_id
      instance_type      = cfg.instance_type
      subnet_id          = cfg.subnet_id
      private_ip         = cfg.private_ip
      security_group_ids = cfg.security_group_ids
      tags               = local.instance_tags[workload]
    }
  }
}

output "planned_data_volumes" {
  description = "Data volume plan keyed by workload and Linux device name."
  value = {
    for key, volume in local.data_volumes : key => {
      snapshot_id       = volume.snapshot_id
      availability_zone = volume.availability_zone
      size              = volume.size_gib
      iops              = volume.iops
      throughput        = volume.throughput
      device_name       = volume.device_name
      volume_role       = volume.volume_role
    }
  }
}
HCL

cat > "${module_dir}/cloud-init/linux-bootstrap.sh.tftpl" <<'TPL'
#!/usr/bin/env bash
set -euo pipefail
cat >/etc/migration-context <<CTX
workload=${workload}
environment=${environment}
application=${application}
cutover_id=${cutover_id}
migration_wave=${migration_wave}
source_os=windows
target_os=linux
CTX
TPL

terraform -chdir=/app/environment/terraform fmt -recursive >/dev/null
