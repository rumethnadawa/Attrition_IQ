"""
=============================================================
  AttritionIQ — GitHub Actions OIDC Setup
  Creates an IAM OIDC Identity Provider + Role so GitHub
  Actions can authenticate to AWS WITHOUT storing long-term
  access keys in GitHub Secrets.

  Run ONCE, then:
    1. Copy the printed Role ARN
    2. Go to GitHub → Settings → Secrets → Add:
         Name : AWS_ROLE_ARN
         Value: <the Role ARN printed below>
    3. Remove AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
       from GitHub Secrets

  Usage: python setup_oidc.py --repo rumethnadawa/Attrition_IQ
=============================================================
"""

import boto3
import json
import os
import argparse
from dotenv import load_dotenv

load_dotenv()

REGION     = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
ROLE_NAME  = "AttritionIQ-GitHubActions-Role"
OIDC_URL   = "token.actions.githubusercontent.com"
OIDC_THUMBPRINT = "6938fd4d98bab03faadb97b34396831e3780aea1"


def get_account_id():
    sts = boto3.client("sts", region_name=REGION)
    return sts.get_caller_identity()["Account"]


def setup_oidc_provider(iam, account_id):
    """Create GitHub OIDC identity provider (only once per account)."""
    provider_arn = f"arn:aws:iam::{account_id}:oidc-provider/{OIDC_URL}"

    try:
        iam.get_open_id_connect_provider(OpenIDConnectProviderArn=provider_arn)
        print(f"  -> OIDC provider already exists: {provider_arn}")
    except iam.exceptions.NoSuchEntityException:
        iam.create_open_id_connect_provider(
            Url=f"https://{OIDC_URL}",
            ClientIDList=["sts.amazonaws.com"],
            ThumbprintList=[OIDC_THUMBPRINT],
        )
        print(f"  -> OIDC provider created: {provider_arn}")

    return provider_arn


def setup_iam_role(iam, provider_arn, repo: str, account_id: str):
    """Create IAM role trusted by the specific GitHub repo."""

    # Trust policy — only your repo on the AttritionIQ branch can assume this role
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": provider_arn
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringLike": {
                        f"{OIDC_URL}:sub": f"repo:{repo}:*"
                    },
                    "StringEquals": {
                        f"{OIDC_URL}:aud": "sts.amazonaws.com"
                    }
                }
            }
        ]
    }

    try:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description=f"GitHub Actions OIDC role for {repo}",
            MaxSessionDuration=3600,
        )
        role_arn = role["Role"]["Arn"]
        print(f"  -> Role created: {ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        # Update trust policy in case repo changed
        iam.update_assume_role_policy(
            RoleName=ROLE_NAME,
            PolicyDocument=json.dumps(trust_policy),
        )
        role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        print(f"  -> Role already exists (trust policy updated): {ROLE_NAME}")

    # Attach required policies for the CI/CD pipeline
    policies = [
        "arn:aws:iam::aws:policy/AmazonECS_FullAccess",
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess",
        "arn:aws:iam::aws:policy/AmazonS3FullAccess",
        "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess",
        "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
        "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
        "arn:aws:iam::aws:policy/CloudWatchFullAccess",
    ]
    for policy_arn in policies:
        try:
            iam.attach_role_policy(RoleName=ROLE_NAME, PolicyArn=policy_arn)
        except iam.exceptions.EntityAlreadyExistsException:
            pass

    print(f"  -> Policies attached: {len(policies)} AWS managed policies")
    return role_arn


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo", required=True,
        help="GitHub repo in 'owner/name' format, e.g. rumethnadawa/Attrition_IQ"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  AttritionIQ — GitHub Actions OIDC Setup")
    print("=" * 60)
    print(f"  Repo   : {args.repo}")
    print(f"  Region : {REGION}")
    print()

    iam        = boto3.client("iam")
    account_id = get_account_id()
    print(f"  Account: {account_id}")

    print("\n[1/2] Setting up OIDC Identity Provider...")
    provider_arn = setup_oidc_provider(iam, account_id)

    print("\n[2/2] Creating IAM Role for GitHub Actions...")
    role_arn = setup_iam_role(iam, provider_arn, args.repo, account_id)

    print("\n" + "=" * 60)
    print("  [DONE] OIDC Setup Complete!")
    print("=" * 60)
    print(f"\n  Role ARN: {role_arn}")
    print("""
  NEXT STEPS:
  ─────────────────────────────────────────────────────────
  1. Go to GitHub → your repo → Settings → Secrets & variables
                                → Actions → New repository secret
       Name : AWS_ROLE_ARN
       Value: (paste the Role ARN above)

  2. Delete these OLD secrets (no longer needed):
       - AWS_ACCESS_KEY_ID
       - AWS_SECRET_ACCESS_KEY

  3. deploy.yml is already configured to use OIDC when
     AWS_ROLE_ARN secret is present.
  ─────────────────────────────────────────────────────────
    """)
