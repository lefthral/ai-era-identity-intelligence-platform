# The three Lambda functions that drive the real-time pipeline.
# All use the same IAM role. Each consumes from Kinesis and writes to
# its respective downstream store.

resource "aws_lambda_function" "feature_computer" {
  function_name    = "${local.name_prefix}-feature-computer"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.handler"
  runtime          = "python3.11"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      ENVIRONMENT           = "aws"
      OFFLINE_BUCKET        = aws_s3_bucket.features.id
      DYNAMODB_TABLE        = aws_dynamodb_table.online_features.name
      NEO4J_URI             = var.neo4j_uri
      NEO4J_USER            = var.neo4j_user
      NEO4J_PASSWORD        = var.neo4j_password
    }
  }

  vpc_config {
    # Public subnets by default. Adjust to your VPC if you put RDS in a private subnet.
    subnet_ids         = []
    security_group_ids = []
  }
}

# Event source mapping: Kinesis -> Lambda
resource "aws_lambda_event_source_mapping" "feature_computer_kinesis" {
  function_name    = aws_lambda_function.feature_computer.arn
  event_source_arn = aws_kinesis_stream.events.arn
  starting_position = "TRIM_HORIZON"
  batch_size        = 100
  enabled           = true
}

# Scorer lambda (separate function with same wiring — one shared zip for the demo)
resource "aws_lambda_function" "scorer" {
  function_name    = "${local.name_prefix}-scorer"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.handler"
  runtime          = "python3.11"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = 60
  memory_size      = 1024

  environment {
    variables = {
      ENVIRONMENT    = "aws"
      DATABASE_URL   = "postgresql+psycopg2://${var.rds_username}:${var.rds_password}@${aws_db_instance.postgres.address}:5432/${var.rds_db_name}"
      DYNAMODB_TABLE = aws_dynamodb_table.online_features.name
      MODEL_PATH     = "s3://${aws_s3_bucket.models.id}/xgb_v1.ubj"
    }
  }
}

# Graph updater lambda
resource "aws_lambda_function" "graph_updater" {
  function_name    = "${local.name_prefix}-graph-updater"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.handler"
  runtime          = "python3.11"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = 300
  memory_size      = 1024

  environment {
    variables = {
      ENVIRONMENT = "aws"
      NEO4J_URI   = var.neo4j_uri
      NEO4J_USER  = var.neo4j_user
      NEO4J_PASSWORD = var.neo4j_password
    }
  }
}
