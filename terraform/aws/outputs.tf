# Useful outputs

output "kinesis_stream_name" {
  value = aws_kinesis_stream.events.name
}

output "kinesis_stream_arn" {
  value = aws_kinesis_stream.events.arn
}

output "features_bucket" {
  value = aws_s3_bucket.features.id
}

output "models_bucket" {
  value = aws_s3_bucket.models.id
}

output "lambda_artifacts_bucket" {
  value = aws_s3_bucket.lambda_artifacts.id
}

output "online_features_table" {
  value = aws_dynamodb_table.online_features.name
}

output "model_registry_table" {
  value = aws_dynamodb_table.model_registry.name
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "mlflow_host_public_dns" {
  value = aws_instance.mlflow.public_dns
}

output "feature_computer_lambda" {
  value = aws_lambda_function.feature_computer.function_name
}

output "scorer_lambda" {
  value = aws_lambda_function.scorer.function_name
}

output "graph_updater_lambda" {
  value = aws_lambda_function.graph_updater.function_name
}
