# RDS Postgres: operational store for decisions, cases, audit log.
# Free tier: db.t3.micro, 20 GB, 750 hrs/month for 12 months.

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = data.aws_subnets.default.ids
  tags = {
    Name = "${local.name_prefix}-db-subnets"
  }
}

data "aws_subnets" "default" {
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Allow Postgres inbound from the VPC"

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]  # Adjust to your VPC CIDR
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres" {
  identifier              = "${local.name_prefix}-postgres"
  engine                  = "postgres"
  engine_version          = "16.3"
  instance_class          = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage_gb
  storage_type            = "gp3"
  db_name                 = var.rds_db_name
  username                = var.rds_username
  password                = var.rds_password
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  skip_final_snapshot     = true
  publicly_accessible     = false
  backup_retention_period = 7
  multi_az                = false
  storage_encrypted       = true
  deletion_protection     = false  # Set true in prod

  # Free-tier cost control
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}
