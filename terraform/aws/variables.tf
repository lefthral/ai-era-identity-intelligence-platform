# AWS Terraform root variables
# All values default to free-tier eligible configurations.

variable "aws_region" {
  description = "AWS region. us-east-1 is the canonical free-tier region."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project prefix applied to all resources."
  type        = string
  default     = "idintel"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "kinesis_shard_count" {
  description = "Kinesis shard count. 1 shard = 1 MB/s write, 2 MB/s read — enough for MVP."
  type        = number
  default     = 1
}

variable "kinesis_retention_hours" {
  description = "How long Kinesis keeps events. 24h is the default (free up to 24h)."
  type        = number
  default     = 24
}

variable "rds_instance_class" {
  description = "RDS instance class. db.t3.micro is free-tier eligible."
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage_gb" {
  description = "RDS storage. 20 GB is the free-tier max."
  type        = number
  default     = 20
}

variable "rds_db_name" {
  type    = string
  default = "identity_intel"
}

variable "rds_username" {
  type    = string
  default = "idintel"
}

variable "rds_password" {
  description = "Override via TF_VAR_rds_password in CI/CD; never commit a real password."
  type        = string
  default     = "CHANGE_ME_LOCAL_DEV_ONLY"
  sensitive   = true
}

variable "ec2_instance_type" {
  description = "EC2 type for the MLflow host. t3.micro is free-tier eligible."
  type        = string
  default     = "t3.micro"
}

variable "ec2_ami_id" {
  description = "AMI ID for the MLflow host. Leave empty to use the latest Amazon Linux 2023."
  type        = string
  default     = ""
}

variable "lambda_zip_path" {
  description = "Path to the pre-built Lambda deployment zip (built by scripts/build_lambdas.sh)."
  type        = string
  default     = "build/lambda_feature_computer.zip"
}

variable "neo4j_uri" {
  description = "Neo4j Aura connection URI (free tier). Set via TF_VAR_neo4j_uri."
  type        = string
  default     = "neo4j+s://xxxxxxxx.databases.neo4j.io:7687"
  sensitive   = true
}

variable "neo4j_user" {
  type    = string
  default = "neo4j"
}

variable "neo4j_password" {
  type      = string
  default   = "CHANGE_ME"
  sensitive = true
}
