"""
=============================================================
  AttritionIQ — S3 Security Hardening
  Enables:
    - Block all public access
    - Server-side encryption (AES-256)
    - Versioning (recover deleted/overwritten files)
    - Lifecycle rule (auto-delete old model versions after 90 days)

  Usage: python setup_s3_security.py
=============================================================
"""

import boto3
import os
from dotenv import load_dotenv

load_dotenv()

REGION      = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


def harden_bucket(s3, bucket):

    # ── 1. Block ALL public access ────────────────────────────
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls":       True,
            "IgnorePublicAcls":      True,
            "BlockPublicPolicy":     True,
            "RestrictPublicBuckets": True,
        },
    )
    print("  -> Public access: BLOCKED (all 4 settings)")

    # ── 2. Enable server-side encryption (AES-256) ────────────
    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    },
                    "BucketKeyEnabled": True,
                }
            ]
        },
    )
    print("  -> Encryption: AES-256 (SSE-S3) enabled")

    # ── 3. Enable versioning ──────────────────────────────────
    s3.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )
    print("  -> Versioning: ENABLED (recover deleted/overwritten files)")

    # ── 4. Lifecycle rule — expire old model versions ─────────
    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID":     "expire-old-model-versions",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "models/"},
                    "NoncurrentVersionExpiration": {
                        "NoncurrentDays": 90,      # keep last 90 days of old versions
                    },
                },
                {
                    "ID":     "expire-old-sagemaker-output",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "sagemaker/output/"},
                    "NoncurrentVersionExpiration": {
                        "NoncurrentDays": 30,
                    },
                },
            ]
        },
    )
    print("  -> Lifecycle: Old model versions deleted after 90 days")
    print("     Lifecycle: Old SageMaker outputs deleted after 30 days")


if __name__ == "__main__":
    print("=" * 60)
    print("  AttritionIQ — S3 Security Hardening")
    print("=" * 60)

    if not BUCKET_NAME:
        print("  ERROR: S3_BUCKET_NAME not set in .env")
        print("         Run python setup_s3.py first.")
        exit(1)

    print(f"  Bucket : {BUCKET_NAME}")
    print(f"  Region : {REGION}")
    print()

    s3 = boto3.client("s3", region_name=REGION)

    try:
        harden_bucket(s3, BUCKET_NAME)
        print("\n[DONE] S3 bucket is now hardened!")
        print(f"  Bucket: s3://{BUCKET_NAME}")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        raise
