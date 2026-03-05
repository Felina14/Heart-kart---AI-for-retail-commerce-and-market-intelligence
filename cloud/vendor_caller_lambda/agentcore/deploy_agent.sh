#!/bin/bash
# Deploy Vendor Caller AgentCore Agent

set -e

echo "🚀 Deploying Vendor Caller AgentCore Agent"
echo "==========================================="

AGENT_NAME="vendor-caller-agent"
REGION="us-east-1"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "📍 AWS Account: $ACCOUNT_ID"
echo "📍 Region: $REGION"

# Deploy the agent
echo ""
echo "📋 Deploying agent..."

python3 agent.py

echo ""
echo "✅ DEPLOYMENT COMPLETE!"
