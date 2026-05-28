"""
=============================================================
  AttritionIQ — Post-Deployment Verification Script
  Run by GitHub Actions after ECS deploy to confirm live
=============================================================
"""

import boto3
import time
import sys
import urllib.request
import json
import os


REGION       = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ECS_CLUSTER  = os.environ.get("ECS_CLUSTER",  "attritioniq-cluster")
ECS_SERVICE  = os.environ.get("ECS_SERVICE",  "attritioniq-service")
PORT         = 8000
MAX_ATTEMPTS = 18   # 3 minutes


def get_task_public_ip():
    ecs = boto3.client("ecs", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)

    for attempt in range(MAX_ATTEMPTS):
        tasks = ecs.list_tasks(cluster=ECS_CLUSTER, serviceName=ECS_SERVICE)
        if not tasks["taskArns"]:
            print(f"  .. No tasks yet ({attempt+1}/{MAX_ATTEMPTS})")
            time.sleep(10)
            continue

        detail = ecs.describe_tasks(cluster=ECS_CLUSTER, tasks=tasks["taskArns"])
        task   = detail["tasks"][0]
        status = task.get("lastStatus", "UNKNOWN")
        print(f"  .. Task status: {status} ({attempt+1}/{MAX_ATTEMPTS})")

        if status == "RUNNING":
            for att in task.get("attachments", []):
                if att["type"] == "ElasticNetworkInterface":
                    for d in att["details"]:
                        if d["name"] == "networkInterfaceId":
                            eni = ec2.describe_network_interfaces(
                                NetworkInterfaceIds=[d["value"]]
                            )
                            return eni["NetworkInterfaces"][0].get(
                                "Association", {}
                            ).get("PublicIp")
        time.sleep(10)
    return None


def health_check(public_ip):
    url = f"http://{public_ip}:{PORT}/health"
    print(f"\n  Checking {url}...")
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
                if data.get("status") == "ok":
                    return True, url
        except Exception as e:
            print(f"  .. Retry {attempt+1}/6 — {e}")
            time.sleep(10)
    return False, url


if __name__ == "__main__":
    print("=" * 60)
    print("  AttritionIQ — Deployment Verification")
    print("=" * 60)

    ip = get_task_public_ip()
    if not ip:
        print("[FAILED] Could not get public IP from ECS task.")
        sys.exit(1)

    print(f"\n  Public IP: {ip}")
    success, url = health_check(ip)

    if success:
        print(f"\n  [SUCCESS] AttritionIQ is LIVE!")
        print(f"  URL  : http://{ip}:{PORT}")
        print(f"  API  : http://{ip}:{PORT}/docs")
        print("=" * 60)
    else:
        print(f"\n  [FAILED] Health check failed at {url}")
        sys.exit(1)
