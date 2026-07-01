variable "region" {
  description = "AWS region used only for offline provider planning."
  type        = string
}

variable "common_tags" {
  description = "Tags every planned migration resource must carry."
  type        = map(string)
}

variable "migration_defaults" {
  description = "Shared EC2 hardening and storage defaults for the Windows-to-Linux cutover."
  type = object({
    cutover_id                  = string
    migration_wave              = string
    kms_key_id                  = string
    iam_instance_profile        = string
    disable_api_termination     = bool
    detailed_monitoring         = bool
    ebs_optimized               = bool
    metadata_http_tokens        = string
    metadata_hop_limit          = number
    metadata_instance_tags      = string
    required_ssm_security_group = string
    forbidden_admin_groups      = list(string)
  })
}

variable "legacy_windows_instances" {
  description = "Legacy Windows EC2 inventory to be replaced by Linux instances. The security_group_ids field is the migrated workload allow-list plus any legacy groups that must be filtered before final cutover."
  type = map(object({
    legacy_instance_id = string
    workload           = string
    environment        = string
    application        = string
    cost_center        = string
    owner              = string
    patch_group        = string
    backup_tier        = string
    subnet_id          = string
    availability_zone  = string
    private_ip         = string
    target_ami_id      = string
    instance_type      = string
    security_group_ids = list(string)
    root_gib           = number
    data_volumes = list(object({
      device_name = string
      snapshot_id = string
      size_gib    = number
      volume_role = string
      iops        = number
      throughput  = number
    }))
  }))
}
