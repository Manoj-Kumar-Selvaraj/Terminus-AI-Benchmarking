terraform {
  required_version = ">= 1.6.0, < 2.0.0"
}

locals {
  stage_document = jsondecode(file("${path.module}/stages.json"))
  stages = {
    for stage in local.stage_document.stages : stage.name => stage
    if stage.reserved_concurrency > 1
  }
}

module "pipeline_stage" {
  for_each = local.stages

  source  = "./modules/lambda"
  version = "0.0.0"

  function_name = "settlement-pipeline"
  runtime       = "go1.x"
  handler       = "main"

  create_package         = false
  local_existing_package = "${path.module}/../dist/pipeline.zip"
  publish                = false

  timeout                        = 30
  memory_size                    = 128
  reserved_concurrent_executions = 1

  allowed_triggers = {
    states = {
      principal = "*"
    }
  }

  environment_variables = {
    PIPELINE_STAGE = "unknown"
  }
}
