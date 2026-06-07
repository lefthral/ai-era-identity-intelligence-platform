# Kinesis Data Stream: the real-time event spine.
# 1 shard = 1 MB/s write, 2 MB/s read; enough for Tier 1 MVP traffic.
# Free tier: 1M PUT payload units/month (~$0.015/M after free tier).

resource "aws_kinesis_stream" "events" {
  name             = "${local.name_prefix}-events"
  shard_count      = var.kinesis_shard_count
  retention_period = var.kinesis_retention_hours
  stream_mode_details {
    stream_mode = "PROVISIONED"
  }
  encryption_type = "KMS"
  kms_key_id      = "alias/aws/kinesis"
}

# Firehose delivery stream: optional path to ship Kinesis -> S3 archive
# (separate from the Lambda-driven online path). Stays off by default.
resource "aws_s3_bucket" "firehose_archive" {
  count = 0  # Enable by setting count = 1 if you want long-term archive
  bucket = "${local.name_prefix}-firehose-archive-${random_id.suffix.hex}"
}
