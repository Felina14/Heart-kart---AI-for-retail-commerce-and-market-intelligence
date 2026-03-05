#!/usr/bin/env python3
"""
Deploy HeartKart Vendor Caller to EC2 with auto-SSL
====================================================
Uses the Docker image already in ECR + Caddy reverse proxy with auto-SSL
via sslip.io (free DNS) so Twilio can connect over wss://.

Architecture:
  Internet (Twilio wss://) → Caddy (:443, auto-SSL) → Docker container (:8080)

Creates:
  - IAM instance profile (ECR pull + Bedrock + DynamoDB)
  - Security group (80, 443, 8080, 22)
  - Elastic IP
  - EC2 instance (Amazon Linux 2023, t3.small)
  - User data installs Docker + Caddy, pulls ECR image, starts server
"""

import base64
import boto3
import json
import os
import sys
import time
import traceback
from datetime import datetime

REGION = "us-east-1"
ACCOUNT_ID = None  # set in main()
ECR_IMAGE = None  # set in main()
INSTANCE_TYPE = "t3.small"
KEY_PAIR_NAME = "heartkart-vendor-caller-key"  # will be created if not exists


def get_clients():
    session = boto3.Session(region_name=REGION)
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    return {
        "ec2": session.client("ec2"),
        "ec2r": session.resource("ec2"),
        "iam": session.client("iam"),
        "ecr": session.client("ecr"),
        "ssm_client": session.client("ssm"),
        "account_id": account_id,
    }


# ======================================================================
# STEP 1: Find latest ECR image
# ======================================================================
def get_ecr_image(ecr, account_id):
    repo = "heartkart-vendor-caller"
    uri = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{repo}"
    try:
        resp = ecr.describe_images(
            repositoryName=repo,
            filter={"tagStatus": "TAGGED"},
        )
        images = sorted(
            resp["imageDetails"],
            key=lambda x: x.get("imagePushedAt", datetime.min),
            reverse=True,
        )
        if images:
            tag = images[0]["imageTags"][0] if images[0].get("imageTags") else "latest"
            return f"{uri}:{tag}"
    except Exception:
        pass
    return f"{uri}:latest"


# ======================================================================
# STEP 2: IAM Role + Instance Profile
# ======================================================================
def ensure_iam_role(iam, account_id):
    role_name = "heartkart-vc-ec2-role"
    profile_name = "heartkart-vc-ec2-profile"

    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }

    # Create role
    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="EC2 role for HeartKart Vendor Caller",
        )
        print(f"   ✅ Created role: {role_name}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"   ✅ Role exists: {role_name}")

    # Attach managed policies
    for policy_arn in [
        "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    ]:
        try:
            iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
        except Exception:
            pass

    # Custom inline policy
    custom_policy = {
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
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                "Resource": "*",
            },
        ],
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="VendorCallerPermissions",
        PolicyDocument=json.dumps(custom_policy),
    )

    # Create instance profile
    try:
        iam.create_instance_profile(InstanceProfileName=profile_name)
        print(f"   ✅ Created instance profile: {profile_name}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"   ✅ Instance profile exists: {profile_name}")

    try:
        iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name, RoleName=role_name
        )
    except iam.exceptions.LimitExceededException:
        pass  # already added

    # Wait for propagation
    time.sleep(10)
    profile_arn = f"arn:aws:iam::{account_id}:instance-profile/{profile_name}"
    return profile_arn, profile_name


# ======================================================================
# STEP 3: Security Group
# ======================================================================
def ensure_security_group(ec2):
    sg_name = "heartkart-vendor-caller-sg"

    # Check if exists
    try:
        resp = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [sg_name]}]
        )
        if resp["SecurityGroups"]:
            sg_id = resp["SecurityGroups"][0]["GroupId"]
            print(f"   ✅ Security group exists: {sg_id}")
            return sg_id
    except Exception:
        pass

    # Create
    resp = ec2.create_security_group(
        GroupName=sg_name,
        Description="HeartKart Vendor Caller - HTTP/HTTPS/WebSocket",
    )
    sg_id = resp["GroupId"]

    rules = [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIp": "0.0.0.0/0"},
        {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "CidrIp": "0.0.0.0/0"},
        {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "CidrIp": "0.0.0.0/0"},
        {
            "IpProtocol": "tcp",
            "FromPort": 8080,
            "ToPort": 8080,
            "CidrIp": "0.0.0.0/0",
        },
    ]
    for rule in rules:
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        "IpProtocol": rule["IpProtocol"],
                        "FromPort": rule["FromPort"],
                        "ToPort": rule["ToPort"],
                        "IpRanges": [{"CidrIp": rule["CidrIp"]}],
                    }
                ],
            )
        except Exception:
            pass

    print(f"   ✅ Created security group: {sg_id}")
    return sg_id


# ======================================================================
# STEP 4: Elastic IP
# ======================================================================
def ensure_elastic_ip(ec2):
    # Check for existing unassociated allocation tagged with our service
    try:
        resp = ec2.describe_addresses(
            Filters=[
                {
                    "Name": "tag:Service",
                    "Values": ["heartkart-vendor-caller"],
                }
            ]
        )
        if resp["Addresses"]:
            addr = resp["Addresses"][0]
            print(
                f"   ✅ Elastic IP exists: {addr['PublicIp']} ({addr['AllocationId']})"
            )
            return addr["AllocationId"], addr["PublicIp"]
    except Exception:
        pass

    # Allocate new
    resp = ec2.allocate_address(Domain="vpc")
    alloc_id = resp["AllocationId"]
    public_ip = resp["PublicIp"]

    ec2.create_tags(
        Resources=[alloc_id],
        Tags=[
            {"Key": "Name", "Value": "heartkart-vendor-caller"},
            {"Key": "Service", "Value": "heartkart-vendor-caller"},
        ],
    )

    print(f"   ✅ Allocated Elastic IP: {public_ip} ({alloc_id})")
    return alloc_id, public_ip


# ======================================================================
# STEP 5: Launch EC2
# ======================================================================
def build_user_data(ecr_image, elastic_ip, account_id, twilio_env):
    """Build the cloud-init user data script."""
    ip_dashed = elastic_ip.replace(".", "-")
    domain = f"{ip_dashed}.sslip.io"

    # Build environment variable flags for Docker
    env_flags = [
        f'-e AWS_DEFAULT_REGION={REGION}',
        f'-e AWS_REGION={REGION}',
        f'-e PORT=8080',
        f'-e SERVICE_URL=https://{domain}',
    ]
    if twilio_env.get("TWILIO_ACCOUNT_SID"):
        env_flags.append(f'-e TWILIO_ACCOUNT_SID={twilio_env["TWILIO_ACCOUNT_SID"]}')
    if twilio_env.get("TWILIO_AUTH_TOKEN"):
        env_flags.append(f'-e TWILIO_AUTH_TOKEN={twilio_env["TWILIO_AUTH_TOKEN"]}')
    if twilio_env.get("TWILIO_PHONE_NUMBER"):
        env_flags.append(f'-e TWILIO_PHONE_NUMBER={twilio_env["TWILIO_PHONE_NUMBER"]}')
    env_str = " \\\n  ".join(env_flags)

    script = f"""#!/bin/bash
set -ex
exec > >(tee /var/log/vendor-caller-setup.log) 2>&1
echo "=== HeartKart Vendor Caller Setup ==="
echo "Started: $(date)"

# ---- Install Docker ----
dnf install -y docker
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

# ---- Wait for Elastic IP ----
echo "Waiting for Elastic IP ({elastic_ip})..."
EXPECTED_IP="{elastic_ip}"
for i in $(seq 1 60); do
    TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)
    CURRENT_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)
    if [ "$CURRENT_IP" = "$EXPECTED_IP" ]; then
        echo "Elastic IP associated: $CURRENT_IP"
        break
    fi
    echo "  Waiting... (current: $CURRENT_IP, expected: $EXPECTED_IP)"
    sleep 5
done

# ---- Login to ECR ----
echo "Logging in to ECR..."
aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{REGION}.amazonaws.com

# ---- Pull and run container ----
echo "Pulling Docker image: {ecr_image}"
docker pull {ecr_image}

echo "Starting container..."
docker run -d --name vendor-caller \\
  --network host \\
  --restart always \\
  {env_str} \\
  {ecr_image}

echo "Container started. Waiting for health check..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8080/health | grep -q healthy; then
        echo "Health check passed!"
        break
    fi
    sleep 2
done

# ---- Install Caddy ----
echo "Installing Caddy..."
curl -sLo /usr/local/bin/caddy "https://caddyserver.com/api/download?os=linux&arch=amd64"
chmod +x /usr/local/bin/caddy

# ---- Configure Caddy with auto-SSL ----
DOMAIN="{domain}"
echo "Configuring Caddy for $DOMAIN..."

cat > /etc/Caddyfile << 'CADDYEOF'
{domain} {{
    reverse_proxy localhost:8080
}}
CADDYEOF

# Replace placeholder with actual domain
sed -i "s/{domain}/$DOMAIN/g" /etc/Caddyfile

# ---- Start Caddy ----
echo "Starting Caddy..."
/usr/local/bin/caddy start --config /etc/Caddyfile --adapter caddyfile

echo ""
echo "=== Setup Complete ==="
echo "Health:    https://$DOMAIN/health"
echo "WebSocket: wss://$DOMAIN/media-stream"
echo "REST API:  https://$DOMAIN/api/info"
echo "Finished: $(date)"
"""
    return script


def get_latest_ami(ec2):
    """Get latest Amazon Linux 2023 x86_64 AMI."""
    resp = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-2023*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
            {"Name": "architecture", "Values": ["x86_64"]},
        ],
    )
    images = sorted(
        resp["Images"], key=lambda x: x["CreationDate"], reverse=True
    )
    if not images:
        print("❌ No Amazon Linux 2023 AMI found")
        sys.exit(1)
    ami = images[0]
    print(f"   ✅ AMI: {ami['ImageId']} ({ami['Name'][:60]})")
    return ami["ImageId"]


def check_existing_instance(ec2):
    """Check if we already have a running instance."""
    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Service", "Values": ["heartkart-vendor-caller"]},
            {"Name": "instance-state-name", "Values": ["running", "pending"]},
        ]
    )
    for reservation in resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            return instance["InstanceId"]
    return None


def launch_instance(ec2, ami_id, sg_id, profile_name, user_data):
    instance_id = check_existing_instance(ec2)
    if instance_id:
        print(f"   ✅ Instance already running: {instance_id}")
        return instance_id

    resp = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[sg_id],
        IamInstanceProfile={"Name": profile_name},
        UserData=user_data,
        MetadataOptions={
            "HttpEndpoint": "enabled",
            "HttpTokens": "optional",
            "HttpPutResponseHopLimit": 2,
        },
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "heartkart-vendor-caller"},
                    {"Key": "Service", "Value": "heartkart-vendor-caller"},
                ],
            }
        ],
    )

    instance_id = resp["Instances"][0]["InstanceId"]
    print(f"   ✅ Launched instance: {instance_id}")
    return instance_id


def wait_for_instance(ec2, instance_id):
    print("   ⏳ Waiting for instance to be running...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print("   ✅ Instance is running")


def associate_eip(ec2, instance_id, alloc_id):
    # Check if already associated
    resp = ec2.describe_addresses(AllocationIds=[alloc_id])
    addr = resp["Addresses"][0]
    if addr.get("InstanceId") == instance_id:
        print(f"   ✅ EIP already associated with {instance_id}")
        return

    # Disassociate if associated with another instance
    if addr.get("AssociationId"):
        ec2.disassociate_address(AssociationId=addr["AssociationId"])
        time.sleep(2)

    ec2.associate_address(InstanceId=instance_id, AllocationId=alloc_id)
    print(f"   ✅ Elastic IP associated with {instance_id}")


# ======================================================================
# STEP 6: Wait for service
# ======================================================================
def wait_for_health(elastic_ip, max_wait=300):
    """Poll health endpoint until service is ready."""
    import urllib.request
    import ssl

    domain = f"{elastic_ip.replace('.', '-')}.sslip.io"
    urls = [
        f"http://{elastic_ip}:8080/health",  # Direct (no SSL)
        f"https://{domain}/health",  # Via Caddy (SSL)
    ]

    print(f"   ⏳ Waiting for service (max {max_wait}s)...")

    start = time.time()
    direct_ok = False
    ssl_ok = False

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)

        # Check direct (HTTP)
        if not direct_ok:
            try:
                req = urllib.request.Request(urls[0], method="GET")
                resp = urllib.request.urlopen(req, timeout=5)
                if resp.status == 200:
                    data = json.loads(resp.read())
                    if data.get("status") == "healthy":
                        print(f"      [{elapsed}s] ✅ HTTP direct: healthy")
                        direct_ok = True
            except Exception:
                pass

        # Check SSL (via Caddy)
        if direct_ok and not ssl_ok:
            try:
                req = urllib.request.Request(urls[1], method="GET")
                resp = urllib.request.urlopen(req, timeout=5, context=ctx)
                if resp.status == 200:
                    data = json.loads(resp.read())
                    if data.get("status") == "healthy":
                        print(f"      [{elapsed}s] ✅ HTTPS/SSL: healthy")
                        ssl_ok = True
            except Exception as e:
                if elapsed % 30 == 0:
                    print(f"      [{elapsed}s] ⏳ SSL not ready yet ({type(e).__name__})")

        if direct_ok and ssl_ok:
            return True
        if direct_ok and not ssl_ok and elapsed > 180:
            print("      ⚠️  SSL taking long — Caddy may still be provisioning cert")
            if elapsed > 240:
                print("      ⚠️  Continuing without SSL confirmation")
                return True

        time.sleep(10)

    if direct_ok:
        print("      ⚠️  Direct HTTP works, SSL may still be provisioning")
        return True

    return False


# ======================================================================
# Load Twilio env vars
# ======================================================================
def load_twilio_env():
    env = {}
    # Try to load from .env files
    for path in [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k.startswith("TWILIO_"):
                                env[k] = v
            except Exception:
                pass
            break

    # Also check environment
    for key in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"]:
        if os.getenv(key):
            env[key] = os.getenv(key)

    return env


# ======================================================================
# MAIN
# ======================================================================
def main():
    print("=" * 70)
    print("📞 Deploying HeartKart Vendor Caller to EC2 (auto-SSL)")
    print("=" * 70)

    clients = get_clients()
    account_id = clients["account_id"]
    print(f"\n📍 Region: {REGION}")
    print(f"📍 Account: {account_id}")

    # Load Twilio env
    twilio_env = load_twilio_env()
    if twilio_env.get("TWILIO_ACCOUNT_SID"):
        print(f"📍 Twilio: ✅ found credentials")
    else:
        print(f"📍 Twilio: ❌ not found (can be added later via SSM)")

    # Step 1: Get ECR image
    print("\n📦 Step 1: ECR Image")
    ecr_image = get_ecr_image(clients["ecr"], account_id)
    print(f"   ✅ Image: {ecr_image}")

    # Step 2: IAM role
    print("\n🔑 Step 2: IAM Role + Instance Profile")
    profile_arn, profile_name = ensure_iam_role(clients["iam"], account_id)

    # Step 3: Security group
    print("\n🔒 Step 3: Security Group")
    sg_id = ensure_security_group(clients["ec2"])

    # Step 4: Elastic IP
    print("\n🌐 Step 4: Elastic IP")
    alloc_id, elastic_ip = ensure_elastic_ip(clients["ec2"])
    ip_dashed = elastic_ip.replace(".", "-")
    domain = f"{ip_dashed}.sslip.io"

    # Step 5: Launch EC2
    print("\n🖥️  Step 5: Launch EC2 Instance")
    ami_id = get_latest_ami(clients["ec2"])
    user_data = build_user_data(ecr_image, elastic_ip, account_id, twilio_env)
    instance_id = launch_instance(
        clients["ec2"], ami_id, sg_id, profile_name, user_data
    )
    wait_for_instance(clients["ec2"], instance_id)

    # Associate Elastic IP
    print("\n🔗 Step 6: Associate Elastic IP")
    associate_eip(clients["ec2"], instance_id, alloc_id)

    # Step 7: Wait for service
    print("\n🏥 Step 7: Health Check")
    healthy = wait_for_health(elastic_ip)

    # Done!
    ws_url = f"wss://{domain}/media-stream"
    print("\n" + "=" * 70)
    if healthy:
        print("✅ DEPLOYMENT COMPLETE!")
    else:
        print("⚠️  DEPLOYMENT COMPLETE (service may still be starting)")
    print("=" * 70)
    print(f"   Instance:   {instance_id}")
    print(f"   Elastic IP: {elastic_ip}")
    print(f"   Domain:     {domain}")
    print(f"   Health:     https://{domain}/health")
    print(f"   WebSocket:  {ws_url}")
    print(f"   REST API:   https://{domain}/api/info")
    print(f"   Direct:     http://{elastic_ip}:8080/health")
    print(f"   ECR Image:  {ecr_image}")
    print(f"   Twilio:     {'✅' if twilio_env.get('TWILIO_ACCOUNT_SID') else '❌ add later'}")
    print()
    print("📝 Test commands:")
    print(f"   curl http://{elastic_ip}:8080/health")
    print(f"   curl https://{domain}/health")
    print(f"   curl https://{domain}/api/info")
    print()
    print("📝 For Lambda backend:")
    print(f"   VENDOR_CALLER_URL = 'https://{domain}'")
    print(f"   POST https://{domain}/api/initiate-call")
    print(f"   Twilio WebSocket: {ws_url}")
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
