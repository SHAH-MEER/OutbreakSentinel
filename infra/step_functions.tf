resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project_name}-pipeline"
  role_arn = aws_iam_role.step_functions.arn

  definition = jsonencode({
    Comment = "Weekly NNDSS ingest -> process -> detect (sharded) pipeline"
    StartAt = "Ingest"
    States = {
      Ingest = {
        Type     = "Task"
        Resource = aws_lambda_function.ingest.arn
        Next     = "Process"
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 30
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
      }
      Process = {
        Type     = "Task"
        Resource = aws_lambda_function.process.arn
        Next     = "PrepareShards"
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 30
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
      }
      # Injects the fixed shard-index list alongside the Process step's
      # output (processed_key) — see detect_shard_count in variables.tf
      # and detection/run_detection.py's series_shard for why this is
      # sharded at all rather than one Detect invocation over the whole
      # panel.
      PrepareShards = {
        Type = "Pass"
        Parameters = {
          "processed_key.$" = "$.processed_key"
          shards            = range(var.detect_shard_count)
        }
        Next = "Detect"
      }
      Detect = {
        Type           = "Map"
        ItemsPath      = "$.shards"
        MaxConcurrency = var.detect_shard_count
        ItemSelector = {
          "processed_key.$" = "$.processed_key"
          "shard_index.$"   = "$$.Map.Item.Value"
          num_shards        = var.detect_shard_count
        }
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "DetectShard"
          States = {
            DetectShard = {
              Type     = "Task"
              Resource = aws_lambda_function.detect.arn
              End      = true
              Retry = [{
                ErrorEquals     = ["States.TaskFailed"]
                IntervalSeconds = 30
                MaxAttempts     = 2
                BackoffRate     = 2.0
              }]
            }
          }
        }
        End = true
      }
    }
  })
}
