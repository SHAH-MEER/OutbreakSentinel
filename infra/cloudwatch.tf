resource "aws_cloudwatch_metric_alarm" "pipeline_failed" {
  alarm_name          = "${var.project_name}-pipeline-failed"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 3600
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Fires when a weekly NNDSS pipeline Step Functions execution fails (ingest, process, or detect)."

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.pipeline.arn
  }
}

resource "aws_cloudwatch_metric_alarm" "detect_lambda_errors" {
  alarm_name          = "${var.project_name}-detect-lambda-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 3600
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Fires when the detect Lambda (the one that writes alerts to DynamoDB) errors out."

  dimensions = {
    FunctionName = aws_lambda_function.detect.function_name
  }
}
