#!/usr/bin/env python3
"""
HeartKart AgentCore Deployment Script
=====================================

Deploys all HeartKart AI agents to AWS Bedrock AgentCore Runtime.

Usage:
    python deploy_all.py                  # Deploy all agents
    python deploy_all.py --agent NAME     # Deploy a specific agent
    python deploy_all.py --list           # List all agents
    python deploy_all.py --status         # Check deployment status
    python deploy_all.py --delete NAME    # Delete a specific agent deployment

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - Docker installed and running (for ECR image builds)
    - boto3, strands-agents, bedrock-agentcore-starter-toolkit installed
    - ECR repository created (or script will create it)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

# ============================================================================
# CONFIGURATION
# ============================================================================

AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_ACCOUNT_ID = os.getenv('AWS_ACCOUNT_ID', '')
ECR_REPO_PREFIX = 'heartkart-agents'
AGENTCORE_ROLE_NAME = 'HeartKartAgentCoreRole'

# Agent definitions
AGENTS = {
    'replenishment_planner': {
        'name': 'HeartKart-Replenishment-Planner',
        'description': 'AI-powered inventory replenishment planning agent',
        'dir': 'replenishment_planner',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
    'stockout_sentinel': {
        'name': 'HeartKart-Stockout-Sentinel',
        'description': 'Real-time stockout risk detection and alerting agent',
        'dir': 'stockout_sentinel',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
    'inventory_copilot': {
        'name': 'HeartKart-Inventory-Copilot',
        'description': 'Natural language inventory query and analytics agent',
        'dir': 'inventory_copilot',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
    'exception_investigator': {
        'name': 'HeartKart-Exception-Investigator',
        'description': 'Inventory anomaly detection and root cause analysis agent',
        'dir': 'exception_investigator',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
    'markdown_coach': {
        'name': 'HeartKart-Markdown-Coach',
        'description': 'Markdown and clearance strategy recommendation agent',
        'dir': 'markdown_coach',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
    'market_intelligence': {
        'name': 'HeartKart-Market-Intelligence',
        'description': 'Competitor pricing and market trend analysis agent',
        'dir': 'market_intelligence',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 1024,
        'timeout_seconds': 180,
    },
    'pricing_intelligence': {
        'name': 'HeartKart-Pricing-Intelligence',
        'description': 'Price optimization and competitive pricing analysis agent',
        'dir': 'pricing_intelligence',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 1024,
        'timeout_seconds': 180,
    },
    'email_drafter': {
        'name': 'HeartKart-Email-Drafter',
        'description': 'Professional purchase order email drafting agent',
        'dir': 'email_drafter',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-pro-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
    'vendor_caller': {
        'name': 'HeartKart-Vendor-Caller',
        'description': 'Vendor call orchestration with fallback logic agent',
        'dir': 'vendor_caller',
        'entry_point': 'agent.py',
        'model_id': 'amazon.nova-lite-v1:0',
        'memory_mb': 512,
        'timeout_seconds': 120,
    },
}

# Base directory for agent code
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================================
# AWS CLIENT HELPERS
# ============================================================================

def get_aws_account_id() -> str:
    """Get the AWS account ID."""
    global AWS_ACCOUNT_ID
    if AWS_ACCOUNT_ID:
        return AWS_ACCOUNT_ID
    try:
        sts = boto3.client('sts', region_name=AWS_REGION)
        identity = sts.get_caller_identity()
        AWS_ACCOUNT_ID = identity['Account']
        return AWS_ACCOUNT_ID
    except Exception as e:
        print(f"❌ Error getting AWS account ID: {e}")
        print("   Set AWS_ACCOUNT_ID environment variable or configure AWS CLI.")
        sys.exit(1)


def get_ecr_client():
    return boto3.client('ecr', region_name=AWS_REGION)


def get_iam_client():
    return boto3.client('iam', region_name=AWS_REGION)


# ============================================================================
# IAM ROLE MANAGEMENT
# ============================================================================

def ensure_agentcore_role() -> str:
    """Create or get the IAM role for AgentCore agents."""
    iam = get_iam_client()
    role_arn = f"arn:aws:iam::{get_aws_account_id()}:role/{AGENTCORE_ROLE_NAME}"

    try:
        iam.get_role(RoleName=AGENTCORE_ROLE_NAME)
        print(f"✅ IAM Role exists: {AGENTCORE_ROLE_NAME}")
        return role_arn
    except ClientError as e:
        if e.response['Error']['Code'] != 'NoSuchEntity':
            raise

    print(f"🔧 Creating IAM Role: {AGENTCORE_ROLE_NAME}...")

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": [
                        "bedrock.amazonaws.com",
                        "agentcore.bedrock.amazonaws.com",
                    ]
                },
                "Action": "sts:AssumeRole",
            }
        ],
    }

    iam.create_role(
        RoleName=AGENTCORE_ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description='HeartKart AgentCore Runtime execution role',
        Tags=[
            {'Key': 'Project', 'Value': 'HeartKart'},
            {'Key': 'ManagedBy', 'Value': 'deploy_all.py'},
        ],
    )

    # Attach required policies
    policies = [
        'arn:aws:iam::aws:policy/AmazonBedrockFullAccess',
        'arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess',
        'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess',
    ]
    for policy_arn in policies:
        try:
            iam.attach_role_policy(RoleName=AGENTCORE_ROLE_NAME, PolicyArn=policy_arn)
            print(f"   ✅ Attached policy: {policy_arn.split('/')[-1]}")
        except Exception as e:
            print(f"   ⚠️ Could not attach {policy_arn}: {e}")

    # Inline policy for DynamoDB write access to specific tables
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:GetItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                ],
                "Resource": [
                    f"arn:aws:dynamodb:{AWS_REGION}:{get_aws_account_id()}:table/valentines-products",
                    f"arn:aws:dynamodb:{AWS_REGION}:{get_aws_account_id()}:table/valentines-products/*",
                    f"arn:aws:dynamodb:{AWS_REGION}:{get_aws_account_id()}:table/heartkart-call-logs",
                    f"arn:aws:dynamodb:{AWS_REGION}:{get_aws_account_id()}:table/heartkart-call-logs/*",
                    f"arn:aws:dynamodb:{AWS_REGION}:{get_aws_account_id()}:table/heartkart-call-logs",
                    f"arn:aws:dynamodb:{AWS_REGION}:{get_aws_account_id()}:table/heartkart-call-logs/*",
                ],
            },
        ],
    }
    iam.put_role_policy(
        RoleName=AGENTCORE_ROLE_NAME,
        PolicyName='HeartKartDynamoDBAccess',
        PolicyDocument=json.dumps(inline_policy),
    )
    print(f"   ✅ Attached inline DynamoDB policy")

    print(f"✅ Created IAM Role: {role_arn}")

    # Wait for role to propagate
    print("   ⏳ Waiting 10s for IAM role propagation...")
    time.sleep(10)

    return role_arn


# ============================================================================
# ECR IMAGE MANAGEMENT
# ============================================================================

def ensure_ecr_repo(agent_key: str) -> str:
    """Create ECR repository for an agent if it doesn't exist."""
    ecr = get_ecr_client()
    repo_name = f"{ECR_REPO_PREFIX}/{agent_key}"

    try:
        response = ecr.describe_repositories(repositoryNames=[repo_name])
        repo_uri = response['repositories'][0]['repositoryUri']
        print(f"✅ ECR repo exists: {repo_name}")
        return repo_uri
    except ClientError as e:
        if e.response['Error']['Code'] != 'RepositoryNotFoundException':
            raise

    print(f"🔧 Creating ECR repo: {repo_name}...")
    response = ecr.create_repository(
        repositoryName=repo_name,
        imageScanningConfiguration={'scanOnPush': True},
        imageTagMutability='MUTABLE',
        tags=[
            {'Key': 'Project', 'Value': 'HeartKart'},
            {'Key': 'Agent', 'Value': agent_key},
        ],
    )
    repo_uri = response['repository']['repositoryUri']
    print(f"✅ Created ECR repo: {repo_uri}")
    return repo_uri


def build_and_push_image(agent_key: str, agent_config: Dict) -> str:
    """Build Docker image and push to ECR."""
    agent_dir = os.path.join(BASE_DIR, agent_config['dir'])
    repo_uri = ensure_ecr_repo(agent_key)
    tag = datetime.now().strftime('%Y%m%d-%H%M%S')
    image_uri = f"{repo_uri}:{tag}"

    # Generate Dockerfile
    dockerfile_path = os.path.join(agent_dir, 'Dockerfile')
    dockerfile_content = f"""FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copy shared data access layer
COPY product_data_access.py /app/product_data_access.py

# Copy agent requirements and install
COPY {agent_config['dir']}/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY {agent_config['dir']}/agent.py /app/agent.py

# Set environment variables
ENV AWS_REGION={AWS_REGION}
ENV BEDROCK_MODEL_ID={agent_config['model_id']}
ENV PYTHONUNBUFFERED=1

# Entry point
CMD ["python", "agent.py"]
"""
    with open(dockerfile_path, 'w') as f:
        f.write(dockerfile_content)

    print(f"📦 Building Docker image for {agent_key}...")

    # Login to ECR
    account_id = get_aws_account_id()
    ecr_login_cmd = (
        f"aws ecr get-login-password --region {AWS_REGION} | "
        f"docker login --username AWS --password-stdin "
        f"{account_id}.dkr.ecr.{AWS_REGION}.amazonaws.com"
    )
    result = subprocess.run(ecr_login_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ ECR login warning: {result.stderr}")

    # Build the image (context is the agentcore_agents directory)
    build_cmd = f"docker build -t {image_uri} -f {dockerfile_path} {BASE_DIR}"
    print(f"   Running: docker build ...")
    result = subprocess.run(build_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Docker build failed: {result.stderr}")
        return ''

    # Push to ECR
    push_cmd = f"docker push {image_uri}"
    print(f"   Pushing to ECR...")
    result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Docker push failed: {result.stderr}")
        return ''

    # Clean up Dockerfile
    os.remove(dockerfile_path)

    print(f"✅ Image pushed: {image_uri}")
    return image_uri


# ============================================================================
# AGENTCORE DEPLOYMENT
# ============================================================================

def deploy_agent(agent_key: str, agent_config: Dict, role_arn: str, skip_build: bool = False) -> Dict:
    """Deploy a single agent to AgentCore."""
    print(f"\n{'='*60}")
    print(f"🚀 Deploying: {agent_config['name']}")
    print(f"{'='*60}")

    agent_dir = os.path.join(BASE_DIR, agent_config['dir'])

    # Verify agent code exists
    agent_file = os.path.join(agent_dir, agent_config['entry_point'])
    if not os.path.exists(agent_file):
        print(f"❌ Agent file not found: {agent_file}")
        return {'status': 'error', 'error': 'Agent file not found'}

    requirements_file = os.path.join(agent_dir, 'requirements.txt')
    if not os.path.exists(requirements_file):
        print(f"❌ Requirements file not found: {requirements_file}")
        return {'status': 'error', 'error': 'Requirements file not found'}

    # Build and push Docker image
    if not skip_build:
        image_uri = build_and_push_image(agent_key, agent_config)
        if not image_uri:
            return {'status': 'error', 'error': 'Image build/push failed'}
    else:
        # Use latest image from ECR
        repo_uri = ensure_ecr_repo(agent_key)
        image_uri = f"{repo_uri}:latest"

    # Deploy to AgentCore via CLI
    print(f"🔧 Registering agent with AgentCore...")

    deploy_config = {
        'agentName': agent_config['name'],
        'description': agent_config['description'],
        'roleArn': role_arn,
        'containerConfig': {
            'imageUri': image_uri,
            'memoryMb': agent_config.get('memory_mb', 512),
            'timeoutSeconds': agent_config.get('timeout_seconds', 120),
            'environment': {
                'AWS_REGION': AWS_REGION,
                'BEDROCK_MODEL_ID': agent_config['model_id'],
                'PRODUCTS_TABLE_NAME': 'valentines-products',
            },
        },
        'tags': {
            'Project': 'HeartKart',
            'Agent': agent_key,
            'DeployedAt': datetime.now().isoformat(),
        },
    }

    # Save deployment config
    config_path = os.path.join(agent_dir, 'deploy_config.json')
    with open(config_path, 'w') as f:
        json.dump(deploy_config, f, indent=2)

    print(f"   📝 Deployment config saved to: {config_path}")

    # Try to deploy via AWS CLI / Bedrock AgentCore API
    try:
        bedrock_agent_client = boto3.client('bedrock-agent', region_name=AWS_REGION)

        # Check if agent already exists
        try:
            agents_response = bedrock_agent_client.list_agents()
            existing = None
            for existing_agent in agents_response.get('agentSummaries', []):
                if existing_agent.get('agentName') == agent_config['name']:
                    existing = existing_agent
                    break

            if existing:
                print(f"   ♻️ Agent already exists (ID: {existing['agentId']}), updating...")
                # Update existing agent
                bedrock_agent_client.update_agent(
                    agentId=existing['agentId'],
                    agentName=agent_config['name'],
                    description=agent_config['description'],
                    agentResourceRoleArn=role_arn,
                    foundationModel=agent_config['model_id'],
                    instruction=f"HeartKart {agent_key} agent for Valentine's Day inventory management.",
                )
                agent_id = existing['agentId']
                print(f"   ✅ Agent updated: {agent_id}")
            else:
                # Create new agent
                response = bedrock_agent_client.create_agent(
                    agentName=agent_config['name'],
                    description=agent_config['description'],
                    agentResourceRoleArn=role_arn,
                    foundationModel=agent_config['model_id'],
                    instruction=f"HeartKart {agent_key} agent for Valentine's Day inventory management.",
                    tags={
                        'Project': 'HeartKart',
                        'Agent': agent_key,
                    },
                )
                agent_id = response['agent']['agentId']
                print(f"   ✅ Agent created: {agent_id}")

            # Prepare the agent
            print(f"   ⏳ Preparing agent...")
            bedrock_agent_client.prepare_agent(agentId=agent_id)

            return {
                'status': 'success',
                'agent_id': agent_id,
                'agent_name': agent_config['name'],
                'image_uri': image_uri,
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['AccessDeniedException', 'ValidationException']:
                print(f"   ⚠️ Bedrock Agent API not available: {error_code}")
                print(f"   📝 Deployment config saved — deploy manually or via AgentCore CLI.")
                return {
                    'status': 'config_saved',
                    'config_path': config_path,
                    'image_uri': image_uri,
                }
            raise

    except Exception as e:
        print(f"   ⚠️ AgentCore deployment API error: {e}")
        print(f"   📝 Deployment config saved — deploy manually or via AgentCore CLI:")
        print(f"      agentcore deploy --config {config_path}")
        return {
            'status': 'config_saved',
            'config_path': config_path,
            'image_uri': image_uri if not skip_build else 'not-built',
        }


def deploy_all_agents(skip_build: bool = False) -> Dict:
    """Deploy all agents to AgentCore."""
    print("=" * 70)
    print("🚀 HeartKart AgentCore Deployment — All Agents")
    print("=" * 70)
    print(f"Region: {AWS_REGION}")
    print(f"Account: {get_aws_account_id()}")
    print(f"Agents: {len(AGENTS)}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Ensure IAM role
    role_arn = ensure_agentcore_role()

    results = {}
    success_count = 0
    fail_count = 0

    for agent_key, agent_config in AGENTS.items():
        try:
            result = deploy_agent(agent_key, agent_config, role_arn, skip_build)
            results[agent_key] = result
            if result.get('status') in ['success', 'config_saved']:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"❌ Failed to deploy {agent_key}: {e}")
            results[agent_key] = {'status': 'error', 'error': str(e)}
            fail_count += 1

    # Summary
    print("\n" + "=" * 70)
    print("📊 DEPLOYMENT SUMMARY")
    print("=" * 70)
    print(f"Total agents:    {len(AGENTS)}")
    print(f"Successful:      {success_count}")
    print(f"Failed:          {fail_count}")
    print()

    for key, result in results.items():
        status_icon = '✅' if result.get('status') in ['success', 'config_saved'] else '❌'
        print(f"  {status_icon} {AGENTS[key]['name']}: {result.get('status', 'unknown')}")
        if result.get('agent_id'):
            print(f"      Agent ID: {result['agent_id']}")
        if result.get('config_path'):
            print(f"      Config: {result['config_path']}")

    # Save deployment manifest
    manifest_path = os.path.join(BASE_DIR, 'deployment_manifest.json')
    manifest = {
        'deployment_time': datetime.now().isoformat(),
        'region': AWS_REGION,
        'account_id': get_aws_account_id(),
        'role_arn': role_arn,
        'agents': results,
    }
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"\n📝 Deployment manifest saved: {manifest_path}")

    return results


def list_agents():
    """List all configured agents."""
    print("=" * 70)
    print("📋 HeartKart AgentCore Agents")
    print("=" * 70)
    print()
    for i, (key, config) in enumerate(AGENTS.items(), 1):
        agent_dir = os.path.join(BASE_DIR, config['dir'])
        agent_file = os.path.join(agent_dir, config['entry_point'])
        exists = "✅" if os.path.exists(agent_file) else "❌"
        print(f"  {i}. {exists} {config['name']}")
        print(f"     Key:   {key}")
        print(f"     Desc:  {config['description']}")
        print(f"     Model: {config['model_id']}")
        print(f"     Dir:   {config['dir']}/")
        print()


def check_status():
    """Check deployment status of all agents."""
    print("=" * 70)
    print("📊 HeartKart AgentCore Deployment Status")
    print("=" * 70)
    print()

    try:
        bedrock_agent = boto3.client('bedrock-agent', region_name=AWS_REGION)
        response = bedrock_agent.list_agents()
        deployed_agents = {a['agentName']: a for a in response.get('agentSummaries', [])}

        for key, config in AGENTS.items():
            name = config['name']
            if name in deployed_agents:
                agent = deployed_agents[name]
                status = agent.get('agentStatus', 'UNKNOWN')
                status_icon = '✅' if status == 'PREPARED' else '⚠️'
                print(f"  {status_icon} {name}: {status}")
                print(f"     Agent ID: {agent.get('agentId', 'N/A')}")
                print(f"     Updated:  {agent.get('updatedAt', 'N/A')}")
            else:
                print(f"  ❌ {name}: NOT DEPLOYED")
            print()

    except Exception as e:
        print(f"⚠️ Could not check status: {e}")
        print("   This may be because the Bedrock Agent API is not available in your region")
        print("   or your credentials don't have access.")

        # Check for deployment configs instead
        print("\n   Checking local deployment configs...")
        for key, config in AGENTS.items():
            config_path = os.path.join(BASE_DIR, config['dir'], 'deploy_config.json')
            if os.path.exists(config_path):
                print(f"  📝 {config['name']}: config saved ({config_path})")
            else:
                print(f"  ❌ {config['name']}: no deployment config")


def delete_agent(agent_name: str):
    """Delete a deployed agent."""
    print(f"🗑️ Deleting agent: {agent_name}...")

    try:
        bedrock_agent = boto3.client('bedrock-agent', region_name=AWS_REGION)
        response = bedrock_agent.list_agents()

        for agent in response.get('agentSummaries', []):
            if agent['agentName'] == agent_name:
                bedrock_agent.delete_agent(
                    agentId=agent['agentId'],
                    skipResourceInUseCheck=True,
                )
                print(f"✅ Agent deleted: {agent_name} (ID: {agent['agentId']})")
                return

        print(f"⚠️ Agent not found: {agent_name}")

    except Exception as e:
        print(f"❌ Error deleting agent: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='HeartKart AgentCore Deployment Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deploy_all.py                           Deploy all agents
  python deploy_all.py --agent replenishment_planner  Deploy single agent
  python deploy_all.py --list                    List all agents
  python deploy_all.py --status                  Check deployment status
  python deploy_all.py --skip-build              Deploy without rebuilding images
  python deploy_all.py --delete HeartKart-Stockout-Sentinel  Delete an agent
        """,
    )
    parser.add_argument('--agent', type=str, help='Deploy a specific agent by key name')
    parser.add_argument('--list', action='store_true', help='List all agents')
    parser.add_argument('--status', action='store_true', help='Check deployment status')
    parser.add_argument('--delete', type=str, help='Delete a specific agent by name')
    parser.add_argument('--skip-build', action='store_true', help='Skip Docker build/push')
    parser.add_argument('--region', type=str, default=AWS_REGION, help='AWS region')

    args = parser.parse_args()

    global AWS_REGION
    AWS_REGION = args.region

    if args.list:
        list_agents()
    elif args.status:
        check_status()
    elif args.delete:
        delete_agent(args.delete)
    elif args.agent:
        if args.agent not in AGENTS:
            print(f"❌ Unknown agent: {args.agent}")
            print(f"   Available: {', '.join(AGENTS.keys())}")
            sys.exit(1)
        role_arn = ensure_agentcore_role()
        deploy_agent(args.agent, AGENTS[args.agent], role_arn, args.skip_build)
    else:
        deploy_all_agents(args.skip_build)


if __name__ == '__main__':
    main()
