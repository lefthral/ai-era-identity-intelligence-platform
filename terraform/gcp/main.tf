# GCP Terraform — portability reference.
# Mirrors the AWS layout 1:1 with equivalent managed services.
# Run with: cd terraform/gcp && terraform init && terraform apply

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

variable "gcp_project_id" {
  type    = string
  default = "idintel-dev"
}

variable "gcp_region" {
  type    = string
  default = "us-central1"
}

variable "project_name" {
  type    = string
  default = "idintel"
}

variable "environment" {
  type    = string
  default = "dev"
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# --- Pub/Sub: event topic (Kinesis equivalent) ---
resource "google_pubsub_topic" "events" {
  name    = "${local.name_prefix}-events"
  message_retention_duration = "86400s"  # 24h free
}

resource "google_pubsub_subscription" "scorer_sub" {
  name    = "${local.name_prefix}-scorer-sub"
  topic   = google_pubsub_topic.events.name
  ack_deadline_seconds = 60
  message_retention_duration = "604800s"

  push_config {
    push_endpoint = ""  # Set to scorer Cloud Run URL
  }
}

# --- GCS: feature + model buckets ---
resource "google_storage_bucket" "features" {
  name     = "${local.name_prefix}-features-${random_id.suffix.hex}"
  location = var.gcp_region
  force_destroy = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "models" {
  name     = "${local.name_prefix}-models-${random_id.suffix.hex}"
  location = var.gcp_region
  force_destroy = true
  uniform_bucket_level_access = true
}

resource "random_id" "suffix" {
  byte_length = 4
}

# --- Firestore: online feature store (DynamoDB equivalent) ---
resource "google_firestore_database" "online" {
  name        = "(default)"
  location_id = var.gcp_region
  type        = "FIRESTORE_NATIVE"

  lifecycle {
    prevent_destroy = false
  }
}

# --- Cloud SQL Postgres: operational store (RDS equivalent) ---
resource "google_sql_database_instance" "postgres" {
  name             = "${local.name_prefix}-postgres"
  database_version = "POSTGRES_16"
  region           = var.gcp_region

  settings {
    tier = "db-f1-micro"  # Free tier
    disk_size = 20
    disk_type  = "PD_SSD"

    ip_configuration {
      ipv4_enabled = false  # Use private IP only
    }
  }
}

resource "google_sql_database" "main" {
  name     = "identity_intel"
  instance = google_sql_database_instance.postgres.name
}

# --- Cloud Run: scorer service (Lambda equivalent) ---
resource "google_cloud_run_service" "scorer" {
  name     = "${local.name_prefix}-scorer"
  location = var.gcp_region

  template {
    spec {
      containers {
        image = "gcr.io/${var.gcp_project_id}/${local.name_prefix}-scorer:latest"
        resources {
          limits = {
            memory = "1Gi"
            cpu    = "1"
          }
        }
        env {
          name  = "ENVIRONMENT"
          value = "gcp"
        }
        env {
          name  = "ONLINE_FEATURES_TABLE"
          value = "online_features"
        }
      }
    }
  }
}

# --- Output ---
output "pubsub_topic" {
  value = google_pubsub_topic.events.name
}
output "features_bucket" {
  value = google_storage_bucket.features.name
}
output "models_bucket" {
  value = google_storage_bucket.models.name
}
output "scorer_url" {
  value = google_cloud_run_service.scorer.status[0].url
}
