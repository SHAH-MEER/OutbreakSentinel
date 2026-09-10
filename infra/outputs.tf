output "raw_bucket" {
  value = aws_s3_bucket.raw.bucket
}

output "processed_bucket" {
  value = aws_s3_bucket.processed.bucket
}

output "alerts_table" {
  value = aws_dynamodb_table.alerts.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.pipeline.repository_url
}

output "dashboard_ecr_repository_url" {
  value = aws_ecr_repository.dashboard.repository_url
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}

output "api_endpoint" {
  value = aws_apigatewayv2_stage.default.invoke_url
}

output "dashboard_url" {
  value = "https://${aws_apprunner_service.dashboard.service_url}"
}
