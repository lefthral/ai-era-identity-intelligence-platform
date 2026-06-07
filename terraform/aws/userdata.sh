#!/bin/bash
# Userdata for the MLflow EC2 host. Installs Docker, MLflow, and starts the
# tracking server against the S3 model bucket.

set -euo pipefail

dnf update -y
dnf install -y docker python3.11 python3.11-pip git
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user

pip3.11 install --quiet --upgrade pip
pip3.11 install --quiet mlflow==2.16.0 boto3

cat > /opt/mlflow.service <<'EOF'
[Unit]
Description=MLflow tracking server
After=docker.target

[Service]
Type=simple
User=ec2-user
Environment=AWS_DEFAULT_REGION=us-east-1
ExecStart=/usr/bin/mlflow server \
  --host 0.0.0.0 \
  --port 5000 \
  --backend-store-uri sqlite:///home/ec2-user/mlflow.db \
  --default-artifact-root s3://__MLFLOW_BUCKET__/
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mlflow.service
systemctl start mlflow.service

echo "MLflow host initialized"
