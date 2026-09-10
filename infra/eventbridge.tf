resource "aws_cloudwatch_event_rule" "weekly_pull" {
  name                = "${var.project_name}-weekly-pull"
  schedule_expression = var.alert_pipeline_schedule
}

resource "aws_cloudwatch_event_target" "pipeline" {
  rule     = aws_cloudwatch_event_rule.weekly_pull.name
  arn      = aws_sfn_state_machine.pipeline.arn
  role_arn = aws_iam_role.eventbridge_sfn.arn
}
