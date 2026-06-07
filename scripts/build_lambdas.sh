#!/usr/bin/env bash
# Build the Lambda deployment zip.
# Packages the three handler folders plus the src/ tree.

set -euo pipefail

cd "$(dirname "$0")/.."

BUILD_DIR="build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Install Python deps to a vendored dir
pip install --quiet --target "$BUILD_DIR/_deps" -r requirements.txt
# Remove platform-specific wheels to keep the zip small and portable
find "$BUILD_DIR/_deps" -name "*.dist-info" -prune -o -name "*.so" -delete || true

# Copy code
cp -R src "$BUILD_DIR/src"
cp -R configs "$BUILD_DIR/configs"
cp -R models "$BUILD_DIR/models" 2>/dev/null || true
cp -R data "$BUILD_DIR/data" 2>/dev/null || true

# Copy each handler to the root of its own zip
for handler in feature_computer graph_updater scorer; do
  cp "lambdas/$handler/handler.py" "$BUILD_DIR/handler.py"
  cd "$BUILD_DIR"
  zip -qr "../$handler.zip" .
  cd ..
  rm "$BUILD_DIR/handler.py"
done

# Also produce a single combined zip (used by default in lambda.tf)
cp "$BUILD_DIR/../scorer.zip" "build/lambda_feature_computer.zip"

echo "Built: feature_computer.zip, graph_updater.zip, scorer.zip"
