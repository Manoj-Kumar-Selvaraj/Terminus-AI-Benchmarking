locals {
  stage_resources = {
    intake            = [aws_s3_bucket.intake.arn]
    verify_manifest   = ["${aws_s3_bucket.intake.arn}/*", aws_kms_key.manifest.arn]
    acquire_lock      = [aws_dynamodb_table.pipeline_checkpoint.arn]
    fetch_inputs      = ["${aws_s3_bucket.intake.arn}/*"]
    validate_inputs   = ["${aws_s3_bucket.intake.arn}/*"]
    transform_records = ["${aws_s3_bucket.work.arn}/*", "${aws_s3_bucket.intake.arn}/*"]
    precheck_ledger   = [aws_dynamodb_table.effect_ledger.arn]
    write_ledger      = [aws_dynamodb_table.effect_ledger.arn]
    build_report      = ["${aws_s3_bucket.reports.arn}/*"]
    notify_partner    = [aws_cloudwatch_event_bus.partner.arn]
    archive_batch     = ["${aws_s3_bucket.intake.arn}/*", "${aws_s3_bucket.archive.arn}/*"]
    release_lock      = [aws_dynamodb_table.pipeline_checkpoint.arn]
  }
}

resource "aws_sfn_state_machine" "settlement_pipeline" {
  name     = "settlement-lambda-cutover"
  role_arn = aws_iam_role.state_machine.arn
  definition = jsonencode({
    Comment = "Twelve-stage settlement pipeline"
    StartAt = "intake"
    States = {
      for index, stage in local.stage_document.stages : stage.name => {
        Type     = "Task"
        Resource = aws_lambda_alias.live[stage.name].arn
        Next     = index < length(local.stage_document.stages) - 1 ? local.stage_document.stages[index + 1].name : null
        End      = index == length(local.stage_document.stages) - 1
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.TooManyRequestsException"]
          IntervalSeconds = 5
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
      }
    }
  })
}
