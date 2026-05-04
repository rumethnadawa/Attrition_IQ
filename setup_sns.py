"""
=============================================================
  AttritionIQ — SNS Alert Setup
  Creates SNS topic and subscribes your email for
  high-risk attrition alerts (>70% leave probability)
  
  Usage: python setup_sns.py --email your@email.com
=============================================================
"""

import boto3
import os
import argparse
from dotenv import load_dotenv

load_dotenv()

REGION     = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
TOPIC_NAME = "AttritionIQ-HighRisk-Alerts"

def setup_sns(email: str):
    sns = boto3.client("sns", region_name=REGION)

    print(f"Creating SNS topic: {TOPIC_NAME}...")
    response  = sns.create_topic(Name=TOPIC_NAME)
    topic_arn = response["TopicArn"]
    print(f"  -> Topic ARN: {topic_arn}")

    print(f"Subscribing {email} to topic...")
    sns.subscribe(
        TopicArn = topic_arn,
        Protocol = "email",
        Endpoint = email,
    )
    print(f"  -> Subscription created. Check {email} inbox and CONFIRM the subscription!")

    # Persist to .env
    lines = []
    found = False
    try:
        with open(".env", "r") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith("SNS_TOPIC_ARN="):
                lines[i] = f"SNS_TOPIC_ARN={topic_arn}\n"
                found = True
    except FileNotFoundError:
        pass
    if not found:
        lines.append(f"\nSNS_TOPIC_ARN={topic_arn}\n")
    with open(".env", "w") as f:
        f.writelines(lines)

    print(f"\n  -> Added SNS_TOPIC_ARN to .env")
    print(f"\n[IMPORTANT] Open your email ({email}) and click CONFIRM SUBSCRIPTION")
    print(f"            before alerts will be delivered.\n")
    return topic_arn


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, help="Email to receive high-risk alerts")
    args = parser.parse_args()
    setup_sns(args.email)
