# EC2 t3.micro instance running MLflow.
# Free tier: 750 hours/month for 12 months.

resource "aws_security_group" "mlflow" {
  name        = "${local.name_prefix}-mlflow-sg"
  description = "Allow MLflow UI inbound (5000) and SSH"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Restrict to your IP in production
  }

  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Restrict to your IP
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["137112412989"]  # Amazon
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_instance" "mlflow" {
  ami                    = var.ec2_ami_id != "" ? var.ec2_ami_id : data.aws_ami.al2023.id
  instance_type          = var.ec2_instance_type
  vpc_security_group_ids = [aws_security_group.mlflow.id]
  iam_instance_profile   = aws_iam_instance_profile.mlflow.name
  user_data              = file("${path.module}/userdata.sh")
  monitoring             = true

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name = "${local.name_prefix}-mlflow-host"
  }
}

resource "aws_iam_role" "mlflow" {
  name = "${local.name_prefix}-mlflow-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "mlflow_s3" {
  name = "${local.name_prefix}-mlflow-s3"
  role = aws_iam_role.mlflow.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ]
      Resource = [
        aws_s3_bucket.models.arn,
        "${aws_s3_bucket.models.arn}/*",
        aws_s3_bucket.features.arn,
        "${aws_s3_bucket.features.arn}/*",
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "mlflow" {
  name = "${local.name_prefix}-mlflow-profile"
  role = aws_iam_role.mlflow.name
}
