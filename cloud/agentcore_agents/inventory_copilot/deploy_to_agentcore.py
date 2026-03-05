#!/usr/bin/env python3
"""Deploy Inventory Copilot Agent to AWS Bedrock AgentCore Runtime"""

from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session
import time, json, sys

def main():
    boto_session = Session()
    region = boto_session.region_name
    
    print("=" * 70)
    print("🚀 Deploying Inventory Copilot Agent to AWS Bedrock AgentCore Runtime")
    print("=" * 70)
    print(f"\n📍 Region: {region}")
    print(f"📍 Account: {boto_session.client('sts').get_caller_identity()['Account']}")
    
    agentcore_runtime = Runtime()
    agent_name = "heartkart_inventory_copilot"
    
    print("\n" + "=" * 70)
    print("📋 Step 1: Configuring deployment...")
    print("=" * 70)
    try:
        agentcore_runtime.configure(
            entrypoint="agent.py", auto_create_execution_role=True,
            auto_create_ecr=True, requirements_file="requirements.txt",
            region=region, agent_name=agent_name
        )
        print("✅ Configuration complete")
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        import traceback; traceback.print_exc()
        return 1
    
    print("\n" + "=" * 70)
    print("🚢 Step 2: Launching agent...")
    print("=" * 70)
    try:
        launch_result = agentcore_runtime.launch()
        print(f"✅ Launch initiated")
        print(f"   - Agent ARN: {launch_result.agent_arn}")
        print(f"   - Agent ID: {launch_result.agent_id}")
        print(f"   - ECR URI: {launch_result.ecr_uri}")
    except Exception as e:
        print(f"❌ Launch failed: {e}")
        import traceback; traceback.print_exc()
        return 1
    
    print("\n" + "=" * 70)
    print("⏳ Step 3: Waiting for deployment...")
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
            print(f"\n❌ Deployment failed: {status}")
            return 1
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        import traceback; traceback.print_exc()
        return 1
    
    print("\n" + "=" * 70)
    print("✅ DEPLOYMENT COMPLETE!")
    print("=" * 70)
    print(f"   - Name: {agent_name}")
    print(f"   - ARN: {launch_result.agent_arn}")
    print(f"   - ID: {launch_result.agent_id}")
    print(f"   - ECR: {launch_result.ecr_uri}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted"); sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc(); sys.exit(1)
