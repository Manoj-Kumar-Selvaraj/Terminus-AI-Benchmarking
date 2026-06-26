resource "aws_dynamodb_table" "pipeline_checkpoint" {
  name         = "settlement-pipeline-checkpoint"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "execution_id"
  attribute { name = "execution_id" type = "S" }
}
resource "aws_dynamodb_table" "effect_ledger" {
  name         = "settlement-pipeline-effect-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "operation_id"
  attribute { name = "operation_id" type = "S" }
}
resource "aws_s3_bucket" "intake" { bucket = "settlement-intake-offline-fixture" }
resource "aws_s3_bucket" "work" { bucket = "settlement-work-offline-fixture" }
resource "aws_s3_bucket" "reports" { bucket = "settlement-reports-offline-fixture" }
resource "aws_s3_bucket" "archive" { bucket = "settlement-archive-offline-fixture" }
resource "aws_kms_key" "manifest" { description = "Manifest verification key" }
resource "aws_cloudwatch_event_bus" "partner" { name = "settlement-partner-events" }
resource "aws_iam_role" "state_machine" { name = "settlement-pipeline-state-machine" assume_role_policy = "{}" }
