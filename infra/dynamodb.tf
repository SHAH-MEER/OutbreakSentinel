resource "aws_dynamodb_table" "alerts" {
  name         = "${var.project_name}-alerts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "region_disease"
  range_key    = "week_id"

  attribute {
    name = "region_disease"
    type = "S"
  }

  attribute {
    name = "week_id"
    type = "S"
  }
}
