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
    state fans out into. Scoring the full NNDSS panel (~17.6k series) in
    one invocation was benchmarked at ~789s even maxing out a single
    Lambda's process pool (6 vCPUs, the ceiling at max Lambda memory) —
    too close to the 900s hard timeout to trust once real Lambda vCPUs
    (usually slower per-core than a dev machine) and cold starts are
    factored in. Sharding the panel across this many independent
    invocations (see detection/run_detection.py's series_shard) gives each
    one a comfortable safety margin instead. 10 shards puts each
    invocation's estimated runtime around 200s at 2 vCPUs (see
    detection/README.md) — ~4x margin under the cap.
  EOT
  type        = number
  default     = 10
}
