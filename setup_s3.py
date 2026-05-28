import boto3
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

# ─── Guard: skip if bucket already configured ────────────────
existing_bucket = os.getenv("S3_BUCKET_NAME")
if existing_bucket:
    print(f"S3_BUCKET_NAME is already set in .env: {existing_bucket}")
    print("Skipping bucket creation. Delete or clear the key from .env to create a new one.")
    exit(0)

# ─── Create new bucket ───────────────────────────────────────
region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
s3 = boto3.client("s3", region_name=region)
bucket_name = f"hr-attrition-artifacts-{uuid.uuid4().hex[:8]}"

print(f"Creating bucket: {bucket_name}")
try:
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region}
        )
    print("Bucket created successfully!")

    # Persist to .env
    with open(".env", "a") as f:
        f.write(f"\nS3_BUCKET_NAME={bucket_name}\n")
    print(f"Added S3_BUCKET_NAME={bucket_name} to .env")

except Exception as e:
    print(f"Error creating bucket: {e}")
