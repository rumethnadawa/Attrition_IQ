"""
=============================================================
  AttritionIQ — CloudWatch Dashboard + Alarms Setup
  Creates a monitoring dashboard and alarms for:
    - ECS CPU & Memory utilization
    - API error rate (from CloudWatch Logs)
    - Prediction activity

  Usage: python setup_cloudwatch.py
=============================================================
"""

import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv()

REGION       = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
CLUSTER_NAME = "attritioniq-cluster"
SERVICE_NAME = "attritioniq-service"
LOG_GROUP    = "/ecs/attritioniq"
DASHBOARD_NAME = "AttritionIQ-Dashboard"
SNS_TOPIC_ARN  = os.getenv("SNS_TOPIC_ARN", "")

cw = boto3.client("cloudwatch", region_name=REGION)


# ── Dashboard ─────────────────────────────────────────────────
def create_dashboard():
    dashboard_body = {
        "widgets": [
            # ── Row 1: ECS Compute ────────────────────────────
            {
                "type": "metric",
                "x": 0, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "ECS CPU Utilization (%)",
                    "metrics": [[
                        "AWS/ECS", "CPUUtilization",
                        "ClusterName", CLUSTER_NAME,
                        "ServiceName", SERVICE_NAME
                    ]],
                    "period": 300,
                    "stat": "Average",
                    "region": REGION,
                    "view": "timeSeries",
                    "annotations": {
                        "horizontal": [{"label": "Alert threshold", "value": 80}]
                    }
                }
            },
            {
                "type": "metric",
                "x": 12, "y": 0, "width": 12, "height": 6,
                "properties": {
                    "title": "ECS Memory Utilization (%)",
                    "metrics": [[
                        "AWS/ECS", "MemoryUtilization",
                        "ClusterName", CLUSTER_NAME,
                        "ServiceName", SERVICE_NAME
                    ]],
                    "period": 300,
                    "stat": "Average",
                    "region": REGION,
                    "view": "timeSeries",
                    "annotations": {
                        "horizontal": [{"label": "Alert threshold", "value": 80}]
                    }
                }
            },
            # ── Row 2: Alarm Status Widgets ───────────────────
            {
                "type": "alarm",
                "x": 0, "y": 6, "width": 6, "height": 3,
                "properties": {
                    "title": "CPU Alarm",
                    "alarms": [
                        f"arn:aws:cloudwatch:{REGION}:{{}}"
                        f":alarm:AttritionIQ-ECS-CPU-High"
                    ]
                }
            },
            {
                "type": "alarm",
                "x": 6, "y": 6, "width": 6, "height": 3,
                "properties": {
                    "title": "Memory Alarm",
                    "alarms": [
                        f"arn:aws:cloudwatch:{REGION}:{{}}"
                        f":alarm:AttritionIQ-ECS-Memory-High"
                    ]
                }
            },
            # ── Row 3: Log Insights ───────────────────────────
            {
                "type": "log",
                "x": 0, "y": 9, "width": 24, "height": 6,
                "properties": {
                    "title": "Recent API Logs",
                    "query": (
                        f"SOURCE '{LOG_GROUP}' | fields @timestamp, @message "
                        "| sort @timestamp desc | limit 50"
                    ),
                    "region": REGION,
                    "view": "table"
                }
            },
        ]
    }

    cw.put_dashboard(
        DashboardName=DASHBOARD_NAME,
        DashboardBody=json.dumps(dashboard_body)
    )
    print(f"  -> Dashboard : {DASHBOARD_NAME}")
    print(f"  -> URL       : https://{REGION}.console.aws.amazon.com/"
          f"cloudwatch/home?region={REGION}#dashboards:name={DASHBOARD_NAME}")


# ── Alarms ────────────────────────────────────────────────────
def create_alarms():
    alarms = [
        {
            "AlarmName":        "AttritionIQ-ECS-CPU-High",
            "AlarmDescription": "ECS CPU utilization exceeded 80% for 10 min",
            "MetricName":       "CPUUtilization",
            "Namespace":        "AWS/ECS",
            "Dimensions": [
                {"Name": "ClusterName", "Value": CLUSTER_NAME},
                {"Name": "ServiceName", "Value": SERVICE_NAME},
            ],
            "Statistic":            "Average",
            "Period":               300,
            "EvaluationPeriods":    2,
            "Threshold":            80.0,
            "ComparisonOperator":   "GreaterThanThreshold",
            "TreatMissingData":     "notBreaching",
        },
        {
            "AlarmName":        "AttritionIQ-ECS-Memory-High",
            "AlarmDescription": "ECS Memory utilization exceeded 80% for 10 min",
            "MetricName":       "MemoryUtilization",
            "Namespace":        "AWS/ECS",
            "Dimensions": [
                {"Name": "ClusterName", "Value": CLUSTER_NAME},
                {"Name": "ServiceName", "Value": SERVICE_NAME},
            ],
            "Statistic":            "Average",
            "Period":               300,
            "EvaluationPeriods":    2,
            "Threshold":            80.0,
            "ComparisonOperator":   "GreaterThanThreshold",
            "TreatMissingData":     "notBreaching",
        },
    ]

    for alarm in alarms:
        if SNS_TOPIC_ARN:
            alarm["AlarmActions"] = [SNS_TOPIC_ARN]
            alarm["OKActions"]    = [SNS_TOPIC_ARN]
        cw.put_metric_alarm(**alarm)
        print(f"  -> Alarm created : {alarm['AlarmName']}")

    if not SNS_TOPIC_ARN:
        print("  [NOTE] SNS_TOPIC_ARN not set — alarms won't send notifications.")
        print("         Run: python setup_sns.py --email your@email.com first.")


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  AttritionIQ — CloudWatch Monitoring Setup")
    print("=" * 60)
    print(f"  Cluster : {CLUSTER_NAME}")
    print(f"  Service : {SERVICE_NAME}")
    print(f"  Region  : {REGION}")
    print()

    print("[1/2] Creating CloudWatch Dashboard...")
    create_dashboard()

    print("\n[2/2] Creating CloudWatch Alarms...")
    create_alarms()

    print("\n[DONE] Monitoring configured!")
    print("       Open the dashboard URL above to view live metrics.")
