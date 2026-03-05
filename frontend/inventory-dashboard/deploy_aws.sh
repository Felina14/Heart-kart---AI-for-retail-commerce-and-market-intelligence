#!/bin/bash

# Deploy Next.js Frontend to AWS S3 + CloudFront
# This script builds and deploys the inventory dashboard

set -e

echo "🚀 Deploying Inventory Dashboard to AWS S3 + CloudFront..."

# Configuration
BUCKET_NAME="inventory-dashboard-frontend"
REGION="us-east-1"
STACK_NAME="inventory-dashboard-frontend"

# Navigate to the dashboard directory
cd "$(dirname "$0")"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first."
    exit 1
fi

echo "📦 Installing dependencies..."
npm install

echo "🔨 Building Next.js application for static export..."
npm run build

echo "📤 Exporting static files..."
# Next.js will output to 'out' directory with static export

echo "☁️  Creating S3 bucket and CloudFront distribution..."

# Deploy CloudFormation stack
aws cloudformation deploy \
  --template-file cloudformation-frontend.yaml \
  --stack-name $STACK_NAME \
  --parameter-overrides BucketName=$BUCKET_NAME \
  --capabilities CAPABILITY_IAM \
  --region $REGION

echo "📤 Uploading files to S3..."

# Get bucket name from CloudFormation output
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
  --output text \
  --region $REGION)

# Sync the out directory to S3
aws s3 sync out/ s3://$BUCKET/ \
  --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "*.html" \
  --region $REGION

# Upload HTML files with different cache settings
aws s3 sync out/ s3://$BUCKET/ \
  --exclude "*" \
  --include "*.html" \
  --cache-control "public, max-age=0, must-revalidate" \
  --region $REGION

echo "🔄 Getting CloudFront distribution ID..."
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
  --output text \
  --region $REGION)

echo "♻️  Creating CloudFront invalidation..."
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*" \
  --region $REGION

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Stack Outputs:"
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region $REGION

echo ""
echo "🌐 Your application will be available at the CloudFront URL above in a few minutes."
echo "⏱️  CloudFront distribution may take 10-15 minutes to fully deploy."
