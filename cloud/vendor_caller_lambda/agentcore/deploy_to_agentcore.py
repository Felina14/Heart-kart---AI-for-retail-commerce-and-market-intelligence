#!/usr/bin/env python3
"""
Deploy Replenishment Planner Agent to AWS Bedrock AgentCore Runtime

This script automates the deployment of the Replenishment Planner Agent to AgentCore Runtime.
"""

from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session
import time
import json
import sys

def main():
    """Deploy the Replenishment Planner Agent to AgentCore Runtime"""
    
    # Initialize
    boto_session = Session()
    region = boto_session.region_name
    
    print("=" * 70)
    print("🚀 Deploying Vendor Caller Agent to AWS Bedrock AgentCore")
    print("=" * 70)
    print(f"\n📍 Region: {region}")
    print(f"📍 Account: {boto_session.client('sts').get_caller_identity()['Account']}")
    
    agentcore_runtime = Runtime()
    agent_name = "vendor_caller_agent"
    
    # Step 1: Configure
    print("\n" + "=" * 70)
    print("📋 Step 1: Configuring deployment...")
    print("=" * 70)
    try:
        response = agentcore_runtime.configure(
            entrypoint="agent.py",
            auto_create_execution_role=True,
            auto_create_ecr=True,
            requirements_file="requirements.txt",
            region=region,
            agent_name=agent_name
        )
        print("✅ Configuration complete")
        print(f"   - Entrypoint: agent.py")
        print(f"   - Requirements: requirements.txt")
        print(f"   - Auto-create IAM role: Yes")
        print(f"   - Auto-create ECR: Yes")
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        return 1
    
    # Step 2: Launch
    print("\n" + "=" * 70)
    print("🚢 Step 2: Launching agent to AgentCore Runtime...")
    print("=" * 70)
    print("   This will:")
    print("   1. Build Docker container from your code")
    print("   2. Push container to Amazon ECR")
    print("   3. Create AgentCore Runtime endpoint")
    print("   4. Deploy your agent")
    print()
    
    try:
        launch_result = agentcore_runtime.launch()
        print("✅ Launch initiated successfully")
        print(f"   - Agent ARN: {launch_result.agent_arn}")
        print(f"   - Agent ID: {launch_result.agent_id}")
        print(f"   - ECR URI: {launch_result.ecr_uri}")
    except Exception as e:
        print(f"❌ Launch failed: {e}")
        return 1
    
    # Step 3: Wait for deployment
    print("\n" + "=" * 70)
    print("⏳ Step 3: Waiting for deployment to complete...")
    print("=" * 70)
    
    try:
        status_response = agentcore_runtime.status()
        status = status_response.endpoint['status']
        end_status = ['READY', 'CREATE_FAILED', 'DELETE_FAILED', 'UPDATE_FAILED']
        
        iteration = 0
        while status not in end_status:
            iteration += 1
            time.sleep(10)
            status_response = agentcore_runtime.status()
            status = status_response.endpoint['status']
            print(f"   [{iteration * 10}s] Status: {status}")
        
        if status == 'READY':
            print(f"\n✅ Deployment successful! Status: {status}")
        else:
            print(f"\n❌ Deployment failed with status: {status}")
            return 1
            
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return 1
    
    # Step 4: Test invocation
    print("\n" + "=" * 70)
    print("🧪 Step 4: Testing agent with sample request...")
    print("=" * 70)
    
    test_payload = {
        "action": "generate_plan"
    }
    
    print(f"   Request: {json.dumps(test_payload, indent=2)}")
    
    try:
        invoke_response = agentcore_runtime.invoke(test_payload)
        print("\n✅ Test invocation successful!")
        
        # Show summary if available
        if isinstance(invoke_response, dict) and 'summary' in invoke_response:
            summary = invoke_response['summary']
            print(f"\n📊 Replenishment Plan Summary:")
            print(f"   - Products needing reorder: {summary.get('total_products_needing_reorder', 0)}")
            print(f"   - Critical urgency: {summary.get('critical_urgency', 0)}")
            print(f"   - High urgency: {summary.get('high_urgency', 0)}")
            print(f"   - Total estimated cost: ${summary.get('total_estimated_cost', 0):,.2f}")
        else:
            print(f"   Response: {json.dumps(invoke_response, indent=2, default=str)[:500]}...")
            
    except Exception as e:
        print(f"\n⚠️  Test invocation failed: {e}")
        print("   (Agent is deployed but test failed - check logs)")
    
    # Summary
    print("\n" + "=" * 70)
    print("✅ DEPLOYMENT COMPLETE!")
    print("=" * 70)
    print(f"\n📦 Agent Details:")
    print(f"   - Name: {agent_name}")
    print(f"   - ARN: {launch_result.agent_arn}")
    print(f"   - ID: {launch_result.agent_id}")
    print(f"   - Region: {region}")
    print(f"   - ECR: {launch_result.ecr_uri}")
    
    print(f"\n🔧 Invoke with boto3:")
    print(f"""
import boto3
import json

client = boto3.client('bedrock-agentcore', region_name='{region}')
response = client.invoke_agent_runtime(
    agentRuntimeArn='{launch_result.agent_arn}',
    qualifier='DEFAULT',
    payload=json.dumps({{"action": "generate_plan"}})
)
""")
    
    print(f"\n📊 View logs:")
    print(f"   aws logs tail /aws/bedrock-agentcore/runtimes/{launch_result.agent_id}-DEFAULT --follow")
    
    print(f"\n🗑️  To delete the agent:")
    print(f"""
import boto3

# Delete runtime
client = boto3.client('bedrock-agentcore-control', region_name='{region}')
client.delete_agent_runtime(agentRuntimeId='{launch_result.agent_id}')

# Delete ECR repository
ecr = boto3.client('ecr', region_name='{region}')
ecr.delete_repository(repositoryName='{launch_result.ecr_uri.split('/')[1]}', force=True)
""")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
