"""
=============================================================
  AttritionIQ — AWS Secrets Manager Setup
  Migrates all .env values to Secrets Manager
  so the ECS container never needs a .env file.
  
  Usage: python setup_secrets.py
=============================================================
"""

import boto3
import os
import json
from dotenv import load_dotenv, dotenv_values

load_dotenv()

REGION      = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
SECRET_NAME = "attritioniq/app-secrets"


def push_secrets():
    sm = boto3.client("secretsmanager", region_name=REGION)

    # Read all current .env values
    env_values = dotenv_values(".env")
    # Remove the key itself from secrets (ECS uses task role, not key)
    secret_payload = {k: v for k, v in env_values.items() if v}

    print(f"Pushing secrets to Secrets Manager: {SECRET_NAME}")
    print(f"  Keys: {list(secret_payload.keys())}")

    try:
        sm.create_secret(
            Name         = SECRET_NAME,
            Description  = "AttritionIQ application secrets",
            SecretString = json.dumps(secret_payload),
        )
        print(f"  -> Secret created: {SECRET_NAME}")
    except sm.exceptions.ResourceExistsException:
        sm.update_secret(
            SecretId     = SECRET_NAME,
            SecretString = json.dumps(secret_payload),
        )
        print(f"  -> Secret updated: {SECRET_NAME}")

    arn = sm.describe_secret(SecretId=SECRET_NAME)["ARN"]
    print(f"  -> Secret ARN: {arn}")
    print(f"\n[DONE] Secrets stored. ECS task role will auto-fetch these at runtime.")
    return arn


def fetch_secrets(secret_name=SECRET_NAME, region=REGION):
    """
    Call this from app.py to load secrets at runtime.
    Returns dict of secret key-value pairs.
    Falls back to environment variables if Secrets Manager unavailable.
    """
    try:
        sm = boto3.client("secretsmanager", region_name=region)
        response = sm.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except Exception as e:
        print(f"[WARNING] Could not fetch from Secrets Manager: {e}")
        return {}


if __name__ == "__main__":
    push_secrets()
