variable "environment" {
  description = "Deployment environment name. Existing stacks depend on the staging name remaining unchanged."
  type        = string
  default     = "staging"
}

variable "vpc_cidr_block" {
  description = "Existing shared VPC CIDR. This module must not reallocate it during refactor recovery."
  type        = string
  default     = "10.42.0.0/16"
}

variable "interface_endpoint_allowed_security_group_ids" {
  description = "Security groups allowed to initiate HTTPS traffic to shared interface endpoints."
  type        = list(string)
  default     = ["sg-app-staging", "sg-batch-staging"]
}

variable "interface_endpoint_allowed_cidr_blocks" {
  description = "Private application CIDRs allowed to initiate HTTPS traffic to shared interface endpoints."
  type        = list(string)
  default     = ["10.42.16.0/20", "10.42.32.0/20"]
}
