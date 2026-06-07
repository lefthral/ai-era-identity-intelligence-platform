# Common locals
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  tags = {
    Project     = "Identity Intelligence Platform"
    Environment = var.environment
    ManagedBy   = "terraform"
    FreeTier    = "true"
  }
}
