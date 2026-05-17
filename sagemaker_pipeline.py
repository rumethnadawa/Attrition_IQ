"""
=============================================================
  AttritionIQ — SageMaker Pipeline Orchestrator (boto3 only)
  Uses boto3 directly — no sagemaker SDK version issues.

  Usage:
    python sagemaker_pipeline.py --mode train
    python sagemaker_pipeline.py --mode deploy
    python sagemaker_pipeline.py --mode all
=============================================================
"""

import boto3
import argparse
import os
import json
import time
import tarfile
import io
from dotenv import load_dotenv

load_dotenv()

REGION     = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET  = os.getenv("S3_BUCKET_NAME")
ENDPOINT   = "attritioniq-endpoint"
JOB_PREFIX = "attritioniq-training"

# SageMaker sklearn 1.2-1 container images per region
SKLEARN_IMAGES = {
    "us-east-1":      "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "us-east-2":      "257758044811.dkr.ecr.us-east-2.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "us-west-1":      "746614075791.dkr.ecr.us-west-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "us-west-2":      "246618743249.dkr.ecr.us-west-2.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "eu-west-1":      "141502667606.dkr.ecr.eu-west-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
    "ap-southeast-1": "475088953585.dkr.ecr.ap-southeast-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3",
}

session    = boto3.Session(region_name=REGION)
sm         = session.client("sagemaker")
sts        = session.client("sts")
account_id = sts.get_caller_identity()["Account"]
IMAGE_URI  = SKLEARN_IMAGES.get(REGION, SKLEARN_IMAGES["us-east-1"])


# ─── IAM Role for SageMaker ──────────────────────────────────
def get_or_create_sagemaker_role():
    iam       = session.client("iam")
    role_name = "AttritionIQ-SageMaker-Role"
    trust     = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect":    "Allow",
            "Principal": {"Service": "sagemaker.amazonaws.com"},
            "Action":    "sts:AssumeRole"
        }]
    })
    try:
        iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=trust)
        for policy in [
            "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess",
            "arn:aws:iam::aws:policy/AmazonS3FullAccess",
        ]:
            iam.attach_role_policy(RoleName=role_name, PolicyArn=policy)
        print(f"  -> Created IAM role: {role_name}")
        time.sleep(10)   # IAM propagation
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"  -> Using existing IAM role: {role_name}")
    return iam.get_role(RoleName=role_name)["Role"]["Arn"]


# ─── Upload Training Data ─────────────────────────────────────
def upload_training_data():
    s3        = session.client("s3")
    local_csv = "WA_Fn-UseC_-HR-Employee-Attrition.csv"
    s3_key    = "sagemaker/input/training/WA_Fn-UseC_-HR-Employee-Attrition.csv"
    print(f"  -> Uploading dataset → s3://{S3_BUCKET}/{s3_key}")
    s3.upload_file(local_csv, S3_BUCKET, s3_key)
    return f"s3://{S3_BUCKET}/sagemaker/input/training"


# ─── Package & Upload Source Code ────────────────────────────
def package_and_upload_source():
    """
    Pack the sagemaker/ directory into sourcedir.tar.gz,
    upload to S3, and return the S3 URI.
    SageMaker will extract this onto the training container.
    """
    s3  = session.client("s3")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add("sagemaker", arcname=".")
    buf.seek(0)
    s3_key = "sagemaker/source/sourcedir.tar.gz"
    s3.upload_fileobj(buf, S3_BUCKET, s3_key)
    uri = f"s3://{S3_BUCKET}/{s3_key}"
    print(f"  -> Uploaded source code → {uri}")
    return uri


# ─── Launch Training Job (boto3 only) ────────────────────────
def run_training(role_arn, job_suffix="latest"):
    print("\n[SageMaker] Launching training job...")
    training_input = upload_training_data()
    source_uri     = package_and_upload_source()

    # Job name: only alphanumeric + hyphens, max 63 chars
    safe_suffix = job_suffix[:7].replace("_", "-")
    job_name    = f"{JOB_PREFIX}-{safe_suffix}"

    print(f"  -> Job name  : {job_name}")
    print(f"  -> Image     : {IMAGE_URI}")
    print(f"  -> Instance  : ml.m5.xlarge (Spot)")

    sm.create_training_job(
        TrainingJobName=job_name,
        AlgorithmSpecification={
            "TrainingImage":     IMAGE_URI,
            "TrainingInputMode": "File",
        },
        RoleArn=role_arn,
        InputDataConfig=[{
            "ChannelName": "training",
            "DataSource": {
                "S3DataSource": {
                    "S3DataType":               "S3Prefix",
                    "S3Uri":                    training_input,
                    "S3DataDistributionType":   "FullyReplicated",
                }
            },
        }],
        OutputDataConfig={
            "S3OutputPath": f"s3://{S3_BUCKET}/sagemaker/output",
        },
        ResourceConfig={
            "InstanceType":    "ml.m5.xlarge",
            "InstanceCount":   1,
            "VolumeSizeInGB":  30,
        },
        HyperParameters={
            # Script settings
            "sagemaker_program":              "train.py",
            "sagemaker_submit_directory":     source_uri,
            "sagemaker_container_log_level":  "20",
            "sagemaker_region":               REGION,
            # Model hyperparameters
            "n-estimators":      "300",
            "max-depth":         "30",
            "min-samples-split": "2",
            "min-samples-leaf":  "1",
            "roc-auc-threshold": "0.70",
            "s3-bucket-name":    S3_BUCKET or "",
        },
        StoppingCondition={
            "MaxRuntimeInSeconds": 3600,
            "MaxWaitTimeInSeconds": 7200,
        },
        EnableManagedSpotTraining=True,
        CheckpointConfig={
            "S3Uri": f"s3://{S3_BUCKET}/sagemaker/checkpoints/{job_name}",
        },
        Tags=[
            {"Key": "Project",   "Value": "AttritionIQ"},
            {"Key": "CommitSHA", "Value": job_suffix},
        ],
    )

    # ── Wait for completion ───────────────────────────────────
    print("  -> Waiting for training to complete (~20-30 min)...")
    waiter = sm.get_waiter("training_job_completed_or_stopped")
    waiter.wait(
        TrainingJobName=job_name,
        WaiterConfig={"Delay": 30, "MaxAttempts": 120},  # up to 60 min
    )

    info       = sm.describe_training_job(TrainingJobName=job_name)
    job_status = info["TrainingJobStatus"]

    if job_status != "Completed":
        reason = info.get("FailureReason", "Unknown")
        raise RuntimeError(f"Training job {job_status}: {reason}")

    model_uri = info["ModelArtifacts"]["S3ModelArtifacts"]
    print(f"\n  -> Training complete!")
    print(f"     Model artifact : {model_uri}")

    # Save for downstream stages
    with open(".sagemaker_model_uri", "w") as f:
        f.write(model_uri)

    return model_uri


# ─── Deploy Endpoint (boto3 only) ────────────────────────────
def deploy_endpoint(model_uri, role_arn):
    print(f"\n[SageMaker] Deploying endpoint: {ENDPOINT}...")

    model_name  = f"attritioniq-model-{int(time.time())}"
    config_name = f"attritioniq-config-{int(time.time())}"

    # Delete existing endpoint if present
    try:
        sm.delete_endpoint(EndpointName=ENDPOINT)
        print("  -> Deleting existing endpoint...")
        waiter = sm.get_waiter("endpoint_deleted")
        waiter.wait(EndpointName=ENDPOINT)
    except sm.exceptions.ClientError:
        pass

    # Create model
    sm.create_model(
        ModelName=model_name,
        PrimaryContainer={
            "Image":         IMAGE_URI,
            "ModelDataUrl":  model_uri,
            "Environment": {
                "SAGEMAKER_PROGRAM":             "inference.py",
                "SAGEMAKER_SUBMIT_DIRECTORY":    model_uri,
                "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
                "SAGEMAKER_REGION":              REGION,
            },
        },
        ExecutionRoleArn=role_arn,
    )

    # Create endpoint config
    sm.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[{
            "VariantName":          "AllTraffic",
            "ModelName":            model_name,
            "InitialInstanceCount": 1,
            "InstanceType":         "ml.t2.medium",
        }],
    )

    # Create endpoint
    sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=config_name)
    print(f"  -> Waiting for endpoint to become InService...")
    waiter = sm.get_waiter("endpoint_in_service")
    waiter.wait(EndpointName=ENDPOINT)

    print(f"  -> Endpoint LIVE: {ENDPOINT}")
    print(f"     Add to .env: SAGEMAKER_ENDPOINT_NAME={ENDPOINT}")
    _update_env("SAGEMAKER_ENDPOINT_NAME", ENDPOINT)


def _update_env(key, value):
    lines = []
    found = False
    try:
        with open(".env", "r") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found     = True
    except FileNotFoundError:
        pass
    if not found:
        lines.append(f"\n{key}={value}\n")
    with open(".env", "w") as f:
        f.writelines(lines)


# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",       choices=["train", "deploy", "all"], default="all")
    parser.add_argument("--job-suffix", default="manual")
    parser.add_argument("--s3-bucket",  default=S3_BUCKET)
    parser.add_argument("--model-uri",  default=None)
    args = parser.parse_args()

    if args.s3_bucket:
        S3_BUCKET = args.s3_bucket

    print("=" * 60)
    print("  AttritionIQ — SageMaker Pipeline (boto3 direct)")
    print(f"  Mode    : {args.mode}")
    print(f"  Region  : {REGION}")
    print(f"  Bucket  : {S3_BUCKET}")
    print(f"  Account : {account_id}")
    print("=" * 60)

    role_arn  = get_or_create_sagemaker_role()
    model_uri = args.model_uri

    if args.mode in ["train", "all"]:
        model_uri = run_training(role_arn, job_suffix=args.job_suffix)

    if args.mode in ["deploy", "all"]:
        if not model_uri and os.path.exists(".sagemaker_model_uri"):
            with open(".sagemaker_model_uri") as f:
                model_uri = f.read().strip()
        if model_uri:
            deploy_endpoint(model_uri=model_uri, role_arn=role_arn)
        else:
            print("  [SKIP] Deploy: no model URI available. Run train first.")

    print("\n[DONE] SageMaker pipeline complete!")
