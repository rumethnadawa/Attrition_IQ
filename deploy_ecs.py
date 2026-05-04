"""
=============================================================
  AttritionIQ — AWS ECR + ECS Fargate Deployment Script
=============================================================
Steps:
  1. Create ECR repository (if not exists)
  2. Authenticate Docker to ECR
  3. Build Docker image
  4. Tag & Push image to ECR
  5. Create ECS Cluster (if not exists)
  6. Register ECS Task Definition
  7. Create ECS Service with public IP (Fargate)
  8. Wait for service to stabilize & print public URL
"""

import boto3
import base64
import subprocess
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

# ─── Config ──────────────────────────────────────────────────
REGION       = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET    = os.getenv("S3_BUCKET_NAME", "")
APP_NAME     = "attritioniq"
ECR_REPO     = "attritioniq-app"
CLUSTER_NAME = "attritioniq-cluster"
SERVICE_NAME = "attritioniq-service"
TASK_FAMILY  = "attritioniq-task"
CONTAINER    = "attritioniq-container"
PORT         = 8000
CPU          = "1024"   # 1 vCPU
MEMORY       = "2048"   # 2 GB

# ─── AWS Clients ─────────────────────────────────────────────
session   = boto3.Session(region_name=REGION)
ecr       = session.client("ecr")
ecs       = session.client("ecs")
ec2       = session.client("ec2")
iam       = session.client("iam")
logs      = session.client("logs")
sts       = session.client("sts")

account_id = sts.get_caller_identity()["Account"]
ecr_uri    = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com"
image_uri  = f"{ecr_uri}/{ECR_REPO}:latest"

print("=" * 60)
print("  AttritionIQ — ECS Fargate Deployment")
print("=" * 60)
print(f"  Account  : {account_id}")
print(f"  Region   : {REGION}")
print(f"  Image    : {image_uri}")
print()

# ─── Step 1: Create ECR Repository ───────────────────────────
print("[1/7] Creating ECR repository...")
try:
    ecr.create_repository(
        repositoryName=ECR_REPO,
        imageScanningConfiguration={"scanOnPush": True},
        imageTagMutability="MUTABLE"
    )
    print(f"  -> Created ECR repo: {ECR_REPO}")
except ecr.exceptions.RepositoryAlreadyExistsException:
    print(f"  -> ECR repo already exists: {ECR_REPO}")

# ─── Step 2: Docker login to ECR ──────────────────────────────
print("\n[2/7] Authenticating Docker to ECR...")
token = ecr.get_authorization_token()
auth  = token["authorizationData"][0]
raw   = base64.b64decode(auth["authorizationToken"]).decode()
user, pwd = raw.split(":", 1)
registry  = auth["proxyEndpoint"]

result = subprocess.run(
    ["docker", "login", "--username", user, "--password-stdin", registry],
    input=pwd, capture_output=True, text=True
)
if result.returncode != 0:
    print(f"  ! Docker login failed: {result.stderr}")
    exit(1)
print(f"  -> Logged in to {registry}")

# ─── Step 3: Build Docker Image ───────────────────────────────
print("\n[3/7] Building Docker image (this may take a few minutes)...")
build = subprocess.run(
    ["docker", "build", "-t", ECR_REPO, "."],
    capture_output=False  # show build output live
)
if build.returncode != 0:
    print("  ! Docker build failed.")
    exit(1)
print("  -> Docker image built successfully.")

# ─── Step 4: Tag & Push to ECR ───────────────────────────────
print(f"\n[4/7] Tagging & pushing image to ECR...")
subprocess.run(["docker", "tag", f"{ECR_REPO}:latest", image_uri], check=True)
push = subprocess.run(["docker", "push", image_uri], capture_output=False)
if push.returncode != 0:
    print("  ! Docker push failed.")
    exit(1)
print(f"  -> Pushed to {image_uri}")

# ─── Step 5: ECS Cluster ─────────────────────────────────────
print(f"\n[5/7] Creating ECS cluster: {CLUSTER_NAME}...")
ecs.create_cluster(
    clusterName=CLUSTER_NAME,
    capacityProviders=["FARGATE"],
    defaultCapacityProviderStrategy=[{"capacityProvider": "FARGATE", "weight": 1}]
)
print(f"  -> Cluster ready: {CLUSTER_NAME}")

# ─── Step 5b: CloudWatch Log Group ───────────────────────────
log_group = f"/ecs/{APP_NAME}"
try:
    logs.create_log_group(logGroupName=log_group)
    print(f"  -> Created log group: {log_group}")
except logs.exceptions.ResourceAlreadyExistsException:
    print(f"  -> Log group exists: {log_group}")

# ─── Step 5c: ECS Task Execution Role ────────────────────────
ROLE_NAME = "ecsTaskExecutionRole"
trust_policy = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
})
try:
    role = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=trust_policy,
        Description="ECS Task Execution Role for AttritionIQ"
    )
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
    )
    # Also attach S3 and DynamoDB access
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
    )
    iam.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
    )
    print(f"  -> Created IAM role: {ROLE_NAME}")
    time.sleep(10)  # wait for role to propagate
except iam.exceptions.EntityAlreadyExistsException:
    print(f"  -> IAM role exists: {ROLE_NAME}")

role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]

# ─── Step 6: Register Task Definition ────────────────────────
print(f"\n[6/7] Registering ECS task definition: {TASK_FAMILY}...")
task_def = ecs.register_task_definition(
    family=TASK_FAMILY,
    networkMode="awsvpc",
    requiresCompatibilities=["FARGATE"],
    cpu=CPU,
    memory=MEMORY,
    executionRoleArn=role_arn,
    taskRoleArn=role_arn,
    containerDefinitions=[{
        "name": CONTAINER,
        "image": image_uri,
        "essential": True,
        "portMappings": [{"containerPort": PORT, "protocol": "tcp"}],
        "environment": [
            {"name": "AWS_DEFAULT_REGION",  "value": REGION},
            {"name": "S3_BUCKET_NAME",       "value": S3_BUCKET},
        ],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group":         log_group,
                "awslogs-region":        REGION,
                "awslogs-stream-prefix": "ecs"
            }
        }
    }]
)
task_rev = task_def["taskDefinition"]["taskDefinitionArn"]
print(f"  -> Task definition registered: {task_rev}")

# ─── Step 7: Get VPC / Subnets / Security Group ──────────────
print(f"\n[7/7] Deploying ECS Fargate service...")

# Use default VPC
vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
vpc_id = vpcs["Vpcs"][0]["VpcId"]

subnets = ec2.describe_subnets(
    Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
)
subnet_ids = [s["SubnetId"] for s in subnets["Subnets"]][:2]  # use first 2

# Create security group for port 8000
sg_name = f"{APP_NAME}-sg"
try:
    sg = ec2.create_security_group(
        GroupName=sg_name,
        Description=f"AttritionIQ ECS security group",
        VpcId=vpc_id
    )
    sg_id = sg["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp",
            "FromPort": PORT,
            "ToPort": PORT,
            "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
        }]
    )
    print(f"  -> Created security group: {sg_id}")
except ec2.exceptions.ClientError as e:
    if "InvalidGroup.Duplicate" in str(e):
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [sg_name]}]
        )
        sg_id = sgs["SecurityGroups"][0]["GroupId"]
        print(f"  -> Using existing security group: {sg_id}")
    else:
        raise

# Delete existing service if present to avoid conflicts
try:
    ecs.update_service(cluster=CLUSTER_NAME, service=SERVICE_NAME, desiredCount=0)
    ecs.delete_service(cluster=CLUSTER_NAME, service=SERVICE_NAME)
    print("  -> Deleted old service, waiting...")
    time.sleep(15)
except Exception:
    pass

# Create ECS Service
service = ecs.create_service(
    cluster=CLUSTER_NAME,
    serviceName=SERVICE_NAME,
    taskDefinition=task_rev,
    desiredCount=1,
    launchType="FARGATE",
    networkConfiguration={
        "awsvpcConfiguration": {
            "subnets":        subnet_ids,
            "securityGroups": [sg_id],
            "assignPublicIp": "ENABLED"
        }
    }
)
print(f"  -> Service created: {SERVICE_NAME}")

# ─── Wait for Task to Start & Get Public IP ──────────────────
print("\n  Waiting for task to start (up to 3 min)...")
public_ip = None
for attempt in range(18):  # up to 3 minutes
    time.sleep(10)
    tasks = ecs.list_tasks(cluster=CLUSTER_NAME, serviceName=SERVICE_NAME)
    if not tasks["taskArns"]:
        print(f"  .. waiting for task assignment ({attempt+1}/18)")
        continue

    task_detail = ecs.describe_tasks(cluster=CLUSTER_NAME, tasks=tasks["taskArns"])
    task = task_detail["tasks"][0]
    status = task.get("lastStatus", "UNKNOWN")
    print(f"  .. task status: {status} ({attempt+1}/18)")

    if status == "RUNNING":
        # Get ENI → public IP
        for attachment in task.get("attachments", []):
            if attachment["type"] == "ElasticNetworkInterface":
                for detail in attachment["details"]:
                    if detail["name"] == "networkInterfaceId":
                        eni_id = detail["value"]
                        eni = ec2.describe_network_interfaces(
                            NetworkInterfaceIds=[eni_id]
                        )
                        assoc = eni["NetworkInterfaces"][0].get("Association", {})
                        public_ip = assoc.get("PublicIp")
        break

print()
print("=" * 60)
if public_ip:
    print(f"  [DEPLOYED] AttritionIQ is LIVE!")
    print(f"  URL : http://{public_ip}:{PORT}")
    print(f"  API : http://{public_ip}:{PORT}/docs")
    print(f"  Logs: CloudWatch -> {log_group}")
else:
    print("  [DEPLOYED] Service is running but IP not yet assigned.")
    print(f"  Check ECS console -> cluster: {CLUSTER_NAME}")
print("=" * 60)
