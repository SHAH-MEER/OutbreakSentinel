# App Runner service for the Streamlit dashboard (dashboard/Dockerfile).
# App Runner, not Lambda, because it's a long-running server — Streamlit
# holds a persistent WebSocket connection per viewer, which doesn't fit
# Lambda's request/response model the way the API does.

resource "aws_iam_role" "app_runner_access" {
  name = "${var.project_name}-apprunner-ecr-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "app_runner_ecr_access" {
  role       = aws_iam_role.app_runner_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_apprunner_service" "dashboard" {
  service_name = "${var.project_name}-dashboard"

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.app_runner_access.arn
    }
    image_repository {
      image_identifier      = "${aws_ecr_repository.dashboard.repository_url}:${var.dashboard_image_tag}"
      image_repository_type = "ECR"
      image_configuration {
        port = "8501"
        runtime_environment_variables = {
          # The dashboard only ever talks to the API over HTTP (see
          # dashboard/app.py) — never to DynamoDB/S3 directly.
          API_BASE_URL = aws_apigatewayv2_stage.default.invoke_url
        }
      }
    }
    auto_deployments_enabled = false
  }

  instance_configuration {
    cpu    = "1024"
    memory = "2048"
  }
}
