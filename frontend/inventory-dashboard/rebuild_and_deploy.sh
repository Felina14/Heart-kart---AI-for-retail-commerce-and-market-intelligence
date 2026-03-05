#!/bin/bash
# Rebuild frontend with production API URL and redeploy to CloudFront

set -e

echo "🔧 Rebuilding frontend with production API URL..."
echo "========================================="
echo ""

# Check if .env.production exists
if [ ! -f .env.production ]; then
  echo "❌ .env.production not found!"
  echo "   Creating it now..."
  cat > .env.production << 'EOF'
# Production environment variables
NEXT_PUBLIC_API_URL=https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com
NEXT_PUBLIC_DEFAULT_VENDOR_PHONE=+919094840869
EOF
fi

echo "✅ Production environment variables:"
cat .env.production
echo ""

# Clean previous build
echo "🗑️  Cleaning previous build..."
rm -rf .next out
echo ""

# Install dependencies (if needed)
if [ ! -d "node_modules" ]; then
  echo "📦 Installing dependencies..."
  npm install
  echo ""
fi

# Build with production env
echo "🏗️  Building Next.js app..."
npm run build
echo ""

# Check if S3 bucket exists
BUCKET_NAME="heartkart-dashboard"
REGION="us-east-1"

echo "📤 Deploying to S3..."
aws s3 sync out/ s3://$BUCKET_NAME/ \
  --region $REGION \
  --delete \
  --cache-control "public, max-age=3600"

echo ""
echo "🔄 Invalidating CloudFront cache..."
DISTRIBUTION_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Origins.Items[0].DomainName, '$BUCKET_NAME')].Id" \
  --output text \
  --region $REGION)

if [ -n "$DISTRIBUTION_ID" ]; then
  aws cloudfront create-invalidation \
    --distribution-id $DISTRIBUTION_ID \
    --paths "/*" \
    --region $REGION
  echo "✅ CloudFront invalidation created"
else
  echo "⚠️  Could not find CloudFront distribution"
fi

echo ""
echo "=" | tr -d '\n' && printf '%*s\n' 70 | tr ' ' '='
echo "✅ DEPLOYMENT COMPLETE!"
echo "=" | tr -d '\n' && printf '%*s\n' 70 | tr ' ' '='
echo ""
echo "🌐 Your app should be live at:"
echo "   https://d100y0kd7r4rn6.cloudfront.net/"
echo ""
echo "⏳ Note: CloudFront cache invalidation may take a few minutes."
echo "   You can force refresh in your browser with Cmd+Shift+R (Mac)"
echo ""

