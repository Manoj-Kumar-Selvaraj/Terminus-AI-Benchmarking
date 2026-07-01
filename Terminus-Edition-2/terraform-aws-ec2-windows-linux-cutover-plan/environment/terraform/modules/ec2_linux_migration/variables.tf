variable "region" {
  description = "AWS region used only for offline provider planning."
  type        = string
}

variable "common_tags" {
  description = "Common tags inherited from the migration root module."
  type        = map(string)
}

variable "migration_defaults" {
  description = "Shared EC2 hardening and storage defaults for the cutover."
  type        = any
}

variable "legacy_windows_instances" {
  description = "Legacy Windows EC2 inventory to replace with Linux instances."
  type        = any
}
