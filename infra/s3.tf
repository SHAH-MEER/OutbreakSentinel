resource "aws_s3_bucket" "raw" {
  bucket = "${var.project_name}-raw-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "expire-old-raw-pulls"
    status = "Enabled"
    filter {}
    expiration {
      days = 180
    }
  }
}

resource "aws_s3_bucket" "processed" {
  bucket = "${var.project_name}-processed-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "processed" {
  bucket                  = aws_s3_bucket.processed.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id
  rule {
    id     = "expire-old-processed-panels"
    status = "Enabled"
    filter {}
    expiration {
      days = 180
    }
  }
}
