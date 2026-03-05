#!/bin/bash

# Deploy Next.js Frontend to Vercel
# This script deploys the inventory dashboard to Vercel

echo "🚀 Deploying Inventory Dashboard to Vercel..."

# Check if vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "❌ Vercel CLI not found. Installing..."
    npm install -g vercel
fi

# Navigate to the dashboard directory
cd "$(dirname "$0")"

echo "📦 Building the application..."

# Deploy to Vercel (production)
echo "🌐 Deploying to production..."
vercel --prod

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 Next steps:"
echo "1. Set environment variables in Vercel dashboard:"
echo "   - NEXT_PUBLIC_API_URL=https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com"
echo "2. Redeploy after setting environment variables"
echo ""
echo "🔗 Visit your Vercel dashboard: https://vercel.com/dashboard"
