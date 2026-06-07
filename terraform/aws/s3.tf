# S3 buckets for offline feature store, model artifacts, and Lambda deployments.

resource "aws_s3_bucket" "features" {
  bucket = "${local.name_prefix}-features-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "features" {
  bucket = aws_s3_bucket.features.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "features" {
  bucket = aws_s3_bucket.features.id
  rule {
    id     = "expire-old-features"
    status = "Enabled"
    expiration {
      days = 365
    }
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_s3_bucket" "models" {
  bucket = "${local.name_prefix}-models-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket" "lambda_artifacts" {
  bucket = "${local.name_prefix}-lambda-artifacts-${random_id.suffix.hex}"
  force_destroy = true
}

# Block public access on all buckets
resource "aws_s3_bucket_public_access_block" "features" {
  bucket                  = aws_s3_bucket.features.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_public_access_block" "models" {
  bucket                  = aws_s3_bucket.models.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_public_access_block" "lambda_artifacts" {
  bucket                  = aws_s3_bucket.lambda_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
