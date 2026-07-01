provider "aws" {
  region                      = var.region
  access_key                  = "offline"
  secret_key                  = "offline"
  token                       = "offline"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true

  default_tags {
    tags = var.common_tags
  }
}
