import boto3
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client('s3', region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
bucket_name = f"hr-attrition-artifacts-{uuid.uuid4().hex[:8]}"

print(f"Creating bucket: {bucket_name}")
try:
    if os.getenv('AWS_DEFAULT_REGION') == 'us-east-1':
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': os.getenv('AWS_DEFAULT_REGION')}
        )
    print("Bucket created successfully!")
    
    # Append to .env
    with open('.env', 'a') as f:
        f.write(f"\nS3_BUCKET_NAME={bucket_name}\n")
    print("Added S3_BUCKET_NAME to .env")
except Exception as e:
    print(f"Error creating bucket: {e}")
