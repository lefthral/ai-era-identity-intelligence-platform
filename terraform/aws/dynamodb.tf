# DynamoDB tables for the online feature store and model registry.
# Free tier: 25 GB storage + 25 WCU/RCU forever.

# Online feature store: one row per account_id, last 24h of features
resource "aws_dynamodb_table" "online_features" {
  name         = "${local.name_prefix}-online-features"
  billing_mode = "PAY_PER_REQUEST"  # Free tier: 25M read + 25M write / month
  hash_key     = "entity_id"

  attribute {
    name = "entity_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Model registry: one row per (model_name, version)
resource "aws_dynamodb_table" "model_registry" {
  name         = "${local.name_prefix}-model-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "model_name"
  range_key    = "stage"

  attribute {
    name = "model_name"
    type = "S"
  }
  attribute {
    name = "stage"
    type = "S"
  }
}
