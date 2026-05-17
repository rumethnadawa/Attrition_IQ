"""
=============================================================
  AttritionIQ — SageMaker Model Registry Setup
  Creates a Model Package Group so every trained model is
  versioned and must be Approved before production use.

  Usage: python setup_model_registry.py
=============================================================
"""

import boto3
import os
from dotenv import load_dotenv

load_dotenv()

REGION             = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
MODEL_PACKAGE_GROUP = "AttritionIQ-Models"

sm = boto3.client("sagemaker", region_name=REGION)


def create_model_package_group():
    try:
        sm.create_model_package_group(
            ModelPackageGroupName=MODEL_PACKAGE_GROUP,
            ModelPackageGroupDescription=(
                "AttritionIQ — HR Attrition Prediction Models. "
                "Each version is registered here after training and "
                "must be Approved before deployment."
            ),
        )
        print(f"  -> Created Model Package Group: {MODEL_PACKAGE_GROUP}")
    except sm.exceptions.ClientError as e:
        if "already exists" in str(e).lower() or "ConflictException" in str(type(e)):
            print(f"  -> Model Package Group already exists: {MODEL_PACKAGE_GROUP}")
        else:
            raise


def list_registered_models():
    """Print all registered model versions and their approval status."""
    response = sm.list_model_packages(
        ModelPackageGroupName=MODEL_PACKAGE_GROUP,
        SortBy="CreationTime",
        SortOrder="Descending",
    )
    packages = response.get("ModelPackageSummaryList", [])

    if not packages:
        print("  -> No models registered yet.")
        return

    print(f"\n  {'Version':<10} {'Status':<15} {'Created':<25}")
    print(f"  {'-'*10} {'-'*15} {'-'*25}")
    for p in packages:
        version = p["ModelPackageArn"].split("/")[-1]
        status  = p.get("ModelApprovalStatus", "PendingManualApproval")
        created = str(p["CreationTime"])[:19]
        print(f"  {version:<10} {status:<15} {created}")


if __name__ == "__main__":
    print("=" * 60)
    print("  AttritionIQ — SageMaker Model Registry Setup")
    print("=" * 60)
    print(f"  Group  : {MODEL_PACKAGE_GROUP}")
    print(f"  Region : {REGION}")
    print()

    print("[1/2] Creating Model Package Group...")
    create_model_package_group()

    print("\n[2/2] Listing registered models...")
    list_registered_models()

    print("\n[DONE] Model Registry ready!")
    print(f"  View at: https://{REGION}.console.aws.amazon.com/sagemaker/home"
          f"?region={REGION}#/model-registry/{MODEL_PACKAGE_GROUP}")
    print()
    print("  HOW IT WORKS:")
    print("  1. Every SageMaker training job registers the model here")
    print("  2. Status starts as 'PendingManualApproval'")
    print("  3. You approve it in SageMaker Studio → it's ready to deploy")
    print("  4. Only Approved models get deployed to production")
