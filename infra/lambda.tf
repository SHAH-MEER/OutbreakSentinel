locals {
  image_uri = "${aws_ecr_repository.pipeline.repository_url}:${var.lambda_image_tag}"
}

resource "aws_lambda_function" "ingest" {
  function_name = "${var.project_name}-ingest"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  timeout       = 120
  memory_size   = 512

  image_config {
    command = ["infra.lambda_app.handlers.ingest_handler"]
  }

  environment {
    variables = {
      RAW_BUCKET = aws_s3_bucket.raw.bucket
    }
  }
}

resource "aws_lambda_function" "process" {
  function_name = "${var.project_name}-process"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  timeout       = 300
  memory_size   = 1024

  image_config {
    command = ["infra.lambda_app.handlers.process_handler"]
  }

  environment {
    variables = {
      RAW_BUCKET       = aws_s3_bucket.raw.bucket
      PROCESSED_BUCKET = aws_s3_bucket.processed.bucket
    }
  }
}

resource "aws_lambda_function" "detect" {
  function_name = "${var.project_name}-detect"
  role          = aws_iam_role.lambda_exec.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  # Each invocation scores one shard (~1/detect_shard_count of the
  # panel's ~10.2k series — see infra/step_functions.tf and
  # variables.tf), not the whole panel, so this has a large safety
  # margin under Lambda's 900s cap rather than the ~884s-of-900s a
  # single unsharded invocation benchmarked at (serially). 3008MB ~= 2
  # vCPUs, matching run_detection.py's default process-pool width for a
  # shard this size.
  timeout     = 300
  memory_size = 3008

  image_config {
    command = ["infra.lambda_app.handlers.detect_handler"]
  }

  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.bucket
      ALERTS_TABLE     = aws_dynamodb_table.alerts.name
    }
  }
}
