"""
=============================================================
  AttritionIQ — SageMaker Pipeline Orchestrator
  Launches training job + deploys endpoint
  Usage:
    python sagemaker_pipeline.py --mode train
    python sagemaker_pipeline.py --mode deploy
    python sagemaker_pipeline.py --mode all
=============================================================
"""

import boto3
import sagemaker
import argparse
import os
import json
import time
from dotenv import load_dotenv
from sagemaker.sklearn.estimator import SKLearn

load_dotenv()

REGION      = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_BUCKET   = os.getenv("S3_BUCKET_NAME")
ENDPOINT    = "attritioniq-endpoint"
JOB_PREFIX  = "attritioniq-training"

session    = boto3.Session(region_name=REGION)
sm_session = sagemaker.Session(boto_session=session)
sts        = session.client("sts")
account_id = sts.get_caller_identity()["Account"]

# ─── IAM Role for SageMaker ──────────────────────────────────
def get_or_create_sagemaker_role():
    iam = session.client("iam")
    role_name = "AttritionIQ-SageMaker-Role"
    trust = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "sagemaker.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    })
    try:
        role = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=trust)
        for policy in [
            "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess",
            "arn:aws:iam::aws:policy/AmazonS3FullAccess",
        ]:
            iam.attach_role_policy(RoleName=role_name, PolicyArn=policy)
        print(f"  -> Created IAM role: {role_name}")
        time.sleep(10)
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"  -> Using existing IAM role: {role_name}")
    return iam.get_role(RoleName=role_name)["Role"]["Arn"]


# ─── Upload Training Data to S3 ──────────────────────────────
def upload_training_data():
    s3 = session.client("s3")
    local_csv = "WA_Fn-UseC_-HR-Employee-Attrition.csv"
    s3_key    = "sagemaker/input/training/WA_Fn-UseC_-HR-Employee-Attrition.csv"
    print(f"  -> Uploading training data to s3://{S3_BUCKET}/{s3_key}")
    s3.upload_file(local_csv, S3_BUCKET, s3_key)
    return f"s3://{S3_BUCKET}/sagemaker/input/training"


# ─── Launch Training Job ─────────────────────────────────────
def run_training(role_arn, job_suffix="latest"):
    print("\n[SageMaker] Launching training job...")
    training_input = upload_training_data()

    estimator = SKLearn(
        entry_point        = "train.py",
        source_dir         = "sagemaker",
        role               = role_arn,
        instance_type      = "ml.m5.xlarge",
        instance_count     = 1,
        framework_version  = "1.2-1",
        py_version         = "py3",
        sagemaker_session  = sm_session,
        output_path        = f"s3://{S3_BUCKET}/sagemaker/output",
        base_job_name      = JOB_PREFIX,
        hyperparameters    = {
            "n-estimators":      300,
            "max-depth":         30,
            "min-samples-split": 2,
            "min-samples-leaf":  1,
            "roc-auc-threshold": 0.70,
        },
        use_spot_instances      = True,   # Save ~70% cost
        max_wait                = 7200,
        max_run                 = 3600,
    )

    estimator.fit({"training": training_input}, wait=True, logs="All")

    model_uri = estimator.model_data
    print(f"\n  -> Training complete! Model artifact: {model_uri}")

    # Save model URI for deploy step
    with open(".sagemaker_model_uri", "w") as f:
        f.write(model_uri)

    return estimator, model_uri


# ─── Deploy Endpoint ─────────────────────────────────────────
def deploy_endpoint(estimator=None, model_uri=None, role_arn=None):
    print(f"\n[SageMaker] Deploying endpoint: {ENDPOINT}...")
    sm = session.client("sagemaker")

    # Delete existing endpoint if present
    try:
        sm.delete_endpoint(EndpointName=ENDPOINT)
        print("  -> Deleted existing endpoint, waiting...")
        time.sleep(30)
    except sm.exceptions.ClientError:
        pass

    if estimator:
        predictor = estimator.deploy(
            initial_instance_count = 1,
            instance_type          = "ml.t2.medium",
            endpoint_name          = ENDPOINT,
        )
    else:
        from sagemaker.sklearn.model import SKLearnModel
        model = SKLearnModel(
            model_data        = model_uri,
            role              = role_arn,
            entry_point       = "inference.py",
            source_dir        = "sagemaker",
            framework_version = "1.2-1",
            sagemaker_session = sm_session,
        )
        predictor = model.deploy(
            initial_instance_count = 1,
            instance_type          = "ml.t2.medium",
            endpoint_name          = ENDPOINT,
        )

    print(f"  -> Endpoint LIVE: {ENDPOINT}")
    print(f"  -> Add to .env: SAGEMAKER_ENDPOINT_NAME={ENDPOINT}")

    # Auto-update .env
    _update_env("SAGEMAKER_ENDPOINT_NAME", ENDPOINT)
    return predictor


def _update_env(key, value):
    lines = []
    found = False
    try:
        with open(".env", "r") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
    except FileNotFoundError:
        pass
    if not found:
        lines.append(f"\n{key}={value}\n")
    with open(".env", "w") as f:
        f.writelines(lines)
    print(f"  -> Updated .env: {key}={value}")


# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["train", "deploy", "all"], default="all")
    parser.add_argument("--job-suffix", default="manual")
    parser.add_argument("--s3-bucket",  default=S3_BUCKET)
    parser.add_argument("--model-uri",  default=None,
                        help="S3 URI for deploy-only mode")
    args = parser.parse_args()

    if args.s3_bucket:
        S3_BUCKET = args.s3_bucket

    print("=" * 60)
    print("  AttritionIQ — SageMaker Pipeline")
    print(f"  Mode   : {args.mode}")
    print(f"  Region : {REGION}")
    print(f"  Bucket : {S3_BUCKET}")
    print("=" * 60)

    role_arn  = get_or_create_sagemaker_role()
    estimator = None
    model_uri = args.model_uri

    if args.mode in ["train", "all"]:
        estimator, model_uri = run_training(role_arn, job_suffix=args.job_suffix)

    if args.mode in ["deploy", "all"]:
        if not model_uri and os.path.exists(".sagemaker_model_uri"):
            with open(".sagemaker_model_uri") as f:
                model_uri = f.read().strip()
        deploy_endpoint(estimator=estimator, model_uri=model_uri, role_arn=role_arn)

    print("\n[DONE] SageMaker pipeline complete!")
