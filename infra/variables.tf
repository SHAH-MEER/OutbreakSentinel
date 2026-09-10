variable "project_name" {
  description = "Prefix applied to every resource name."
  type        = string
  default     = "outbreak-sentinel"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "lambda_image_tag" {
  description = <<-EOT
    Tag of the pipeline image already pushed to the ECR repo this stack
    creates. There's a bootstrap ordering requirement here: the ECR repo
    must exist and have this tag pushed to it BEFORE the Lambda functions
    can be created, since AWS validates the image exists at apply time.
    See infra/README.md for the two-step apply this requires.
  EOT
  type        = string
  default     = "latest"
}

variable "alert_pipeline_schedule" {
  description = "EventBridge cron expression for the weekly ingestion run. Default: Tuesdays 13:00 UTC, after CDC's typical weekly NNDSS refresh."
  type        = string
  default     = "cron(0 13 ? * TUE *)"
}

variable "detect_shard_count" {
  description = <<-EOT
    Number of parallel Detect Lambda invocations the Step Functions Map
    state fans out into. Scoring the full NNDSS panel (~10.2k series,
    after fixing a region-name casing bug — see data/README.md) in one
    invocation was benchmarked at ~884s serially — over half of the 900s
    hard timeout on its own, before any of the usual production margin
    (real Lambda vCPUs are typically slower per-core than a dev machine;
    cold starts add more). Sharding across this many independent
    invocations (see detection/run_detection.py's series_shard) gives each
    one a large safety margin instead: at 10 shards and 2 vCPUs per
    invocation, each shard's estimated runtime is well under 100s against
    a 300s per-function timeout (see detection/README.md).
  EOT
  type        = number
  default     = 10
}
