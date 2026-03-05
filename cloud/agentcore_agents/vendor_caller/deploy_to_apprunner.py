#!/usr/bin/env python3
"""
Deploy HeartKart Vendor Caller to AWS App Runner
=================================================
Creates all required AWS resources:
  - ECR repository
  - CodeBuild project (builds Docker image)
  - App Runner IAM roles (access + instance)
  - App Runner service

Then updates the service with its own URL (SERVICE_URL) so Twilio
knows where to connect for WebSocket media streams.
"""

import boto3
import io
import json
import os
import sys
import time
import traceback
import zipfile
from datetime import datetime

REGION = "us-east-1"
REPO_NAME = "heartkart-vendor-caller"
SERVICE_NAME = "heartkart-vendor-caller"
PROJECT_NAME = "heartkart-vendor-caller-builder"
BUCKET_PREFIX = "heartkart-vc-build"
IMAGE_TAG = datetime.now().strftime("%Y%m%d-%H%M%S")

# Files to include in the Docker build
SOURCE_FILES = {
    "cloud_server.py": "cloud_server.py",
    "nova_sonic_voice_agent.py": "nova_sonic_voice_agent.py",
    "product_data_access.py": "product_data_access.py",
    "requirements_cloud.txt": "requirements.txt",  # renamed in container
    "Dockerfile.cloud": "Dockerfile",  # renamed in container
}


def get_clients():
    session = boto3.Session(region_name=REGION)
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    return {
        "ecr": session.client("ecr"),
        "s3": session.client("s3"),
        "iam": session.client("iam"),
        "codebuild": session.client("codebuild"),
        "apprunner": session.client("apprunner"),
        "account_id": account_id,
        "session": session,
    }


# ======================================================================
# STEP 1: ECR REPOSITORY
# ======================================================================
def ensure_ecr_repo(ecr, account_id):
    uri = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{REPO_NAME}"
    try:
        ecr.create_repository(repositoryName=REPO_NAME)
        print(f"   ✅ Created ECR repo: {uri}")
    except ecr.exceptions.RepositoryAlreadyExistsException:
        print(f"   ✅ ECR repo exists: {uri}")
    return uri


# ======================================================================
# STEP 2: S3 BUCKET + SOURCE UPLOAD
# ======================================================================
def upload_source(s3, account_id):
    bucket = f"{BUCKET_PREFIX}-{account_id}"
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
        print(f"   ✅ Created S3 bucket: {bucket}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"   ✅ S3 bucket exists: {bucket}")
    except Exception as e:
        if "BucketAlreadyOwnedByYou" in str(e) or "BucketAlreadyExists" in str(e):
            print(f"   ✅ S3 bucket exists: {bucket}")
        else:
            raise

    # Create zip with renamed files
    base_dir = os.path.dirname(os.path.abspath(__file__))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for local_name, zip_name in SOURCE_FILES.items():
            path = os.path.join(base_dir, local_name)
            if not os.path.exists(path):
                print(f"   ❌ Missing file: {path}")
                sys.exit(1)
            zf.write(path, zip_name)
    buf.seek(0)

    key = f"vendor-caller/source-{IMAGE_TAG}.zip"
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
    print(f"   ✅ Uploaded source: s3://{bucket}/{key}")
    return bucket, key


# ======================================================================
# STEP 3: CODEBUILD IAM ROLE
# ======================================================================
def ensure_codebuild_role(iam, account_id):
    role_name = "heartkart-vc-codebuild-role"
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "codebuild.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="CodeBuild role for HeartKart Vendor Caller",
        )
        arn = resp["Role"]["Arn"]
        print(f"   ✅ Created CodeBuild role: {role_name}")
        time.sleep(8)  # wait for propagation
    except iam.exceptions.EntityAlreadyExistsException:
        arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        print(f"   ✅ CodeBuild role exists: {role_name}")

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:PutImage",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                ],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:GetObjectVersion"],
                "Resource": f"arn:aws:s3:::{BUCKET_PREFIX}-{account_id}/*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": "*",
            },
        ],
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="CodeBuildPolicy",
        PolicyDocument=json.dumps(policy),
    )
    return arn


# ======================================================================
# STEP 4: CODEBUILD PROJECT + BUILD
# ======================================================================
def run_codebuild(codebuild, role_arn, ecr_uri, account_id, bucket, key):
    buildspec = f"""version: 0.2
phases:
  pre_build:
    commands:
      - echo Logging in to ECR...
      - aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{REGION}.amazonaws.com
  build:
    commands:
      - echo Building Docker image...
      - docker build -t {REPO_NAME} .
      - docker tag {REPO_NAME}:latest {ecr_uri}:{IMAGE_TAG}
      - docker tag {REPO_NAME}:latest {ecr_uri}:latest
  post_build:
    commands:
      - docker push {ecr_uri}:{IMAGE_TAG}
      - docker push {ecr_uri}:latest
      - echo Build complete
"""

    # Create or update project
    source_cfg = {
        "type": "S3",
        "location": f"{bucket}/{key}",
        "buildspec": buildspec,
    }
    env_cfg = {
        "type": "LINUX_CONTAINER",
        "image": "aws/codebuild/amazonlinux2-x86_64-standard:5.0",
        "computeType": "BUILD_GENERAL1_SMALL",
        "privilegedMode": True,
    }
    try:
        codebuild.create_project(
            name=PROJECT_NAME,
            source=source_cfg,
            artifacts={"type": "NO_ARTIFACTS"},
            environment=env_cfg,
            serviceRole=role_arn,
        )
        print(f"   ✅ Created CodeBuild project: {PROJECT_NAME}")
    except codebuild.exceptions.ResourceAlreadyExistsException:
        codebuild.update_project(
            name=PROJECT_NAME,
            source=source_cfg,
            environment=env_cfg,
            serviceRole=role_arn,
        )
        print(f"   ✅ Updated CodeBuild project: {PROJECT_NAME}")

    # Start build
    build = codebuild.start_build(projectName=PROJECT_NAME)
    build_id = build["build"]["id"]
    print(f"   🔄 Build started: {build_id}")

    # Poll for completion
    while True:
        time.sleep(10)
        resp = codebuild.batch_get_builds(ids=[build_id])
        status = resp["builds"][0]["buildStatus"]
        phase = resp["builds"][0].get("currentPhase", "?")
        print(f"      [{phase}] {status}")
        if status in ("SUCCEEDED", "FAILED", "FAULT", "TIMED_OUT", "STOPPED"):
            break

    if status != "SUCCEEDED":
        # Print build logs for debugging
        logs = resp["builds"][0].get("logs", {})
        print(f"   ❌ Build failed: {status}")
        if logs.get("deepLink"):
            print(f"      Logs: {logs['deepLink']}")
        sys.exit(1)

    print(f"   ✅ Docker image built and pushed: {ecr_uri}:{IMAGE_TAG}")
    return f"{ecr_uri}:{IMAGE_TAG}"


# ======================================================================
# STEP 5: APP RUNNER IAM ROLES
# ======================================================================
def ensure_apprunner_roles(iam, account_id):
    # --- Access Role (ECR pull) ---
    access_role = "heartkart-vc-apprunner-access"
    trust_access = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "build.apprunner.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        iam.create_role(
            RoleName=access_role,
            AssumeRolePolicyDocument=json.dumps(trust_access),
            Description="App Runner ECR access for Vendor Caller",
        )
        print(f"   ✅ Created access role: {access_role}")
        time.sleep(8)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"   ✅ Access role exists: {access_role}")

    iam.attach_role_policy(
        RoleName=access_role,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess",
    )
    access_arn = f"arn:aws:iam::{account_id}:role/{access_role}"

    # --- Instance Role (Bedrock + DynamoDB) ---
    instance_role = "heartkart-vc-apprunner-instance"
    trust_instance = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        iam.create_role(
            RoleName=instance_role,
            AssumeRolePolicyDocument=json.dumps(trust_instance),
            Description="App Runner instance role for Vendor Caller",
        )
        print(f"   ✅ Created instance role: {instance_role}")
        time.sleep(8)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"   ✅ Instance role exists: {instance_role}")

    instance_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeModelWithBidirectionalStream",
                ],
                "Resource": "arn:aws:bedrock:us-east-1::foundation-model/*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:Scan",
                    "dynamodb:Query",
                    "dynamodb:PutItem",
                    "dynamodb:BatchGetItem",
                ],
                "Resource": [
                    f"arn:aws:dynamodb:us-east-1:{account_id}:table/valentines-products",
                    f"arn:aws:dynamodb:us-east-1:{account_id}:table/valentines-products/*",
                    f"arn:aws:dynamodb:us-east-1:{account_id}:table/heartkart-call-logs",
                    f"arn:aws:dynamodb:us-east-1:{account_id}:table/heartkart-call-logs/*",
                    f"arn:aws:dynamodb:us-east-1:{account_id}:table/heartkart-call-logs",
                    f"arn:aws:dynamodb:us-east-1:{account_id}:table/heartkart-call-logs/*",
                ],
            },
        ],
    }
    iam.put_role_policy(
        RoleName=instance_role,
        PolicyName="VendorCallerPermissions",
        PolicyDocument=json.dumps(instance_policy),
    )
    instance_arn = f"arn:aws:iam::{account_id}:role/{instance_role}"

    return access_arn, instance_arn


# ======================================================================
# STEP 6: APP RUNNER SERVICE
# ======================================================================
def create_or_update_service(apprunner, image_uri, access_arn, instance_arn, env_vars):
    # Check if service already exists
    existing_arn = None
    try:
        resp = apprunner.list_services()
        for svc in resp.get("ServiceSummaryList", []):
            if svc["ServiceName"] == SERVICE_NAME:
                existing_arn = svc["ServiceArn"]
                break
    except Exception:
        pass

    runtime_env = {k: v for k, v in env_vars.items() if v}

    source_config = {
        "ImageRepository": {
            "ImageIdentifier": image_uri,
            "ImageConfiguration": {
                "RuntimeEnvironmentVariables": runtime_env,
                "Port": "8080",
            },
            "ImageRepositoryType": "ECR",
        },
        "AutoDeploymentsEnabled": False,
        "AuthenticationConfiguration": {"AccessRoleArn": access_arn},
    }

    health_check = {
        "Protocol": "HTTP",
        "Path": "/health",
        "Interval": 10,
        "Timeout": 5,
        "HealthyThreshold": 1,
        "UnhealthyThreshold": 5,
    }

    instance_config = {
        "Cpu": "1024",  # 1 vCPU
        "Memory": "2048",  # 2 GB
        "InstanceRoleArn": instance_arn,
    }

    if existing_arn:
        print(f"   🔄 Updating existing service: {SERVICE_NAME}")
        resp = apprunner.update_service(
            ServiceArn=existing_arn,
            SourceConfiguration=source_config,
            HealthCheckConfiguration=health_check,
            InstanceConfiguration=instance_config,
        )
        service_arn = existing_arn
    else:
        print(f"   🆕 Creating new service: {SERVICE_NAME}")
        resp = apprunner.create_service(
            ServiceName=SERVICE_NAME,
            SourceConfiguration=source_config,
            HealthCheckConfiguration=health_check,
            InstanceConfiguration=instance_config,
        )
        service_arn = resp["Service"]["ServiceArn"]

    service_url = resp["Service"]["ServiceUrl"]
    print(f"   ✅ Service ARN: {service_arn}")
    print(f"   🌐 URL: https://{service_url}")
    return service_arn, service_url


# ======================================================================
# STEP 7: WAIT FOR RUNNING
# ======================================================================
def wait_for_running(apprunner, service_arn):
    print("   ⏳ Waiting for service to be RUNNING...")
    terminal = {"RUNNING", "CREATE_FAILED", "DELETE_FAILED", "DELETED"}
    iteration = 0
    while True:
        time.sleep(15)
        iteration += 1
        resp = apprunner.describe_service(ServiceArn=service_arn)
        status = resp["Service"]["Status"]
        print(f"      [{iteration * 15}s] {status}")
        if status in terminal:
            break

    if status != "RUNNING":
        print(f"   ❌ Service failed: {status}")
        sys.exit(1)

    url = resp["Service"]["ServiceUrl"]
    print(f"   ✅ Service is RUNNING!")
    print(f"   🌐 URL: https://{url}")
    return url


# ======================================================================
# STEP 8: UPDATE SERVICE_URL
# ======================================================================
def update_service_url(apprunner, service_arn, service_url, env_vars):
    """Update the service's environment with its own URL."""
    env_vars["SERVICE_URL"] = f"https://{service_url}"
    runtime_env = {k: v for k, v in env_vars.items() if v}

    print(f"   🔄 Setting SERVICE_URL = https://{service_url}")
    apprunner.update_service(
        ServiceArn=service_arn,
        SourceConfiguration={
            "ImageRepository": {
                "ImageIdentifier": env_vars.get("_image_uri", ""),
                "ImageConfiguration": {
                    "RuntimeEnvironmentVariables": {
                        k: v for k, v in runtime_env.items() if not k.startswith("_")
                    },
                    "Port": "8080",
                },
                "ImageRepositoryType": "ECR",
            },
            "AutoDeploymentsEnabled": False,
            "AuthenticationConfiguration": {
                "AccessRoleArn": env_vars.get("_access_arn", "")
            },
        },
    )

    # Wait for update to complete
    print("   ⏳ Waiting for update...")
    while True:
        time.sleep(10)
        resp = apprunner.describe_service(ServiceArn=service_arn)
        status = resp["Service"]["Status"]
        if status == "RUNNING":
            break
        print(f"      {status}...")

    print("   ✅ SERVICE_URL configured")


# ======================================================================
# MAIN
# ======================================================================
def main():
    print("=" * 70)
    print("📞 Deploying HeartKart Vendor Caller to AWS App Runner")
    print("=" * 70)

    clients = get_clients()
    account_id = clients["account_id"]
    print(f"\n📍 Region: {REGION}")
    print(f"📍 Account: {account_id}")

    # Collect Twilio env vars (optional — can be added later)
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone = os.getenv("TWILIO_PHONE_NUMBER", "")

    env_vars = {
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
        "PORT": "8080",
        "SERVICE_URL": "",  # will be set after deploy
        "TWILIO_ACCOUNT_SID": twilio_sid,
        "TWILIO_AUTH_TOKEN": twilio_token,
        "TWILIO_PHONE_NUMBER": twilio_phone,
        "USD_TO_INR": "89.6",
    }

    # Step 1: ECR
    print("\n📦 Step 1: ECR Repository")
    ecr_uri = ensure_ecr_repo(clients["ecr"], account_id)

    # Step 2: Upload source
    print("\n📤 Step 2: Upload Source to S3")
    bucket, key = upload_source(clients["s3"], account_id)

    # Step 3: CodeBuild role
    print("\n🔑 Step 3: CodeBuild IAM Role")
    cb_role_arn = ensure_codebuild_role(clients["iam"], account_id)

    # Step 4: Build Docker image
    print("\n🔨 Step 4: Build Docker Image via CodeBuild")
    image_uri = run_codebuild(
        clients["codebuild"], cb_role_arn, ecr_uri, account_id, bucket, key
    )

    # Step 5: App Runner roles
    print("\n🔑 Step 5: App Runner IAM Roles")
    access_arn, instance_arn = ensure_apprunner_roles(clients["iam"], account_id)

    # Step 6: Create App Runner service
    print("\n🚀 Step 6: Create App Runner Service")
    service_arn, service_url = create_or_update_service(
        clients["apprunner"], image_uri, access_arn, instance_arn, env_vars
    )

    # Step 7: Wait for running
    print("\n⏳ Step 7: Wait for Service")
    service_url = wait_for_running(clients["apprunner"], service_arn)

    # Step 8: Update with SERVICE_URL
    print("\n🔧 Step 8: Configure SERVICE_URL")
    env_vars["_image_uri"] = image_uri
    env_vars["_access_arn"] = access_arn
    update_service_url(clients["apprunner"], service_arn, service_url, env_vars)

    # Done!
    ws_url = f"wss://{service_url}/media-stream"
    print("\n" + "=" * 70)
    print("✅ DEPLOYMENT COMPLETE!")
    print("=" * 70)
    print(f"   Service:    {SERVICE_NAME}")
    print(f"   ARN:        {service_arn}")
    print(f"   URL:        https://{service_url}")
    print(f"   Health:     https://{service_url}/health")
    print(f"   WebSocket:  {ws_url}")
    print(f"   REST API:   https://{service_url}/api/info")
    print(f"   Image:      {image_uri}")
    print(f"   Twilio:     {'✅' if twilio_sid else '❌ Set TWILIO_* env vars'}")
    print()
    print("📝 Next steps:")
    print(f"   1. Test health: curl https://{service_url}/health")
    print(f"   2. Test info:   curl https://{service_url}/api/info")
    if not twilio_sid:
        print(
            "   3. Add Twilio credentials via App Runner console or re-deploy with env vars"
        )
    print(
        f"   4. Lambda backend should use: POST https://{service_url}/api/initiate-call"
    )
    print(f"   5. Twilio will connect to: {ws_url}")
    print()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)
