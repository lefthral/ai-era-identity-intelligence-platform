#!/usr/bin/env bash
# Deploy the AWS stack via Terraform.

set -euo pipefail

cd "$(dirname "$0")/.."

# 1. Build the Lambda zips first
bash scripts/build_lambdas.sh

# 2. Upload the zip to the artifacts bucket (idempotent — bucket is created by Terraform)
# The bucket name is available as an output of the apply step.

# 3. Apply
cd terraform/aws
terraform init
terraform apply -auto-approve

# 4. Get the bucket name and upload zips
BUCKET=$(terraform output -raw lambda_artifacts_bucket)
cd ../..
aws s3 cp build/feature_computer.zip "s3://$BUCKET/feature_computer.zip"
aws s3 cp build/graph_updater.zip   "s3://$BUCKET/graph_updater.zip"
aws s3 cp build/scorer.zip          "s3://$BUCKET/scorer.zip"

# 5. Update Lambda function code
FEATURE_FN=$(cd terraform/aws && terraform output -raw feature_computer_lambda)
GRAPH_FN=$(cd terraform/aws && terraform output -raw graph_updater_lambda)
SCORER_FN=$(cd terraform/aws && terraform output -raw scorer_lambda)
REGION=$(grep aws_region terraform/aws/terraform.tfvars 2>/dev/null | cut -d= -f2 | tr -d ' "')
REGION=${REGION:-us-east-1}

aws lambda update-function-code --function-name "$FEATURE_FN" --s3-bucket "$BUCKET" --s3-key feature_computer.zip --region "$REGION"
aws lambda update-function-code --function-name "$GRAPH_FN"   --s3-bucket "$BUCKET" --s3-key graph_updater.zip   --region "$REGION"
aws lambda update-function-code --function-name "$SCORER_FN"  --s3-bucket "$BUCKET" --s3-key scorer.zip          --region "$REGION"

echo "AWS deploy complete. MLflow UI: http://$(cd terraform/aws && terraform output -raw mlflow_host_public_dns):5000"
