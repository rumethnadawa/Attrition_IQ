"""
=============================================================
  AttritionIQ — ECS Auto-Scaling Setup
  Configures Application Auto Scaling for ECS Fargate so the
  service scales out under load and back in when quiet.

  Policy:
    Scale OUT  → when avg CPU > 70% for 2 x 60s periods
    Scale IN   → when avg CPU < 30% for 5 x 60s periods
    Min tasks  : 1  |  Max tasks : 3

  Usage: python setup_autoscaling.py
=============================================================
"""

import boto3
import os
from dotenv import load_dotenv

load_dotenv()

REGION       = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
CLUSTER_NAME = "attritioniq-cluster"
SERVICE_NAME = "attritioniq-service"
MIN_TASKS    = 1
MAX_TASKS    = 3

resource_id  = f"service/{CLUSTER_NAME}/{SERVICE_NAME}"
aas          = boto3.client("application-autoscaling", region_name=REGION)
cw           = boto3.client("cloudwatch", region_name=REGION)


def register_scalable_target():
    """Register the ECS service as an auto-scaling target."""
    aas.register_scalable_target(
        ServiceNamespace  = "ecs",
        ResourceId        = resource_id,
        ScalableDimension = "ecs:service:DesiredCount",
        MinCapacity       = MIN_TASKS,
        MaxCapacity       = MAX_TASKS,
    )
    print(f"  -> Scalable target registered: {resource_id}")
    print(f"     Min tasks: {MIN_TASKS} | Max tasks: {MAX_TASKS}")


def create_scale_out_policy():
    """Scale OUT when CPU > 70% — adds 1 task."""
    response = aas.put_scaling_policy(
        PolicyName        = "AttritionIQ-ScaleOut-CPU",
        ServiceNamespace  = "ecs",
        ResourceId        = resource_id,
        ScalableDimension = "ecs:service:DesiredCount",
        PolicyType        = "StepScaling",
        StepScalingPolicyConfiguration = {
            "AdjustmentType":        "ChangeInCapacity",
            "CooldownSeconds":       120,
            "MetricAggregationType": "Average",
            "StepAdjustments": [
                {
                    "MetricIntervalLowerBound": 0,
                    "ScalingAdjustment":        1,   # add 1 task
                }
            ],
        },
    )
    policy_arn = response["PolicyARN"]
    print(f"  -> Scale-OUT policy created (CPU > 70% → +1 task)")

    # CloudWatch alarm that triggers scale-out
    cw.put_metric_alarm(
        AlarmName          = "AttritionIQ-CPU-High-ScaleOut",
        AlarmDescription   = "Scale out ECS when CPU > 70% for 2 min",
        MetricName         = "CPUUtilization",
        Namespace          = "AWS/ECS",
        Dimensions         = [
            {"Name": "ClusterName", "Value": CLUSTER_NAME},
            {"Name": "ServiceName", "Value": SERVICE_NAME},
        ],
        Statistic          = "Average",
        Period             = 60,
        EvaluationPeriods  = 2,
        Threshold          = 70.0,
        ComparisonOperator = "GreaterThanThreshold",
        AlarmActions       = [policy_arn],
        TreatMissingData   = "notBreaching",
    )
    print(f"     CloudWatch alarm: AttritionIQ-CPU-High-ScaleOut")
    return policy_arn


def create_scale_in_policy():
    """Scale IN when CPU < 30% — removes 1 task."""
    response = aas.put_scaling_policy(
        PolicyName        = "AttritionIQ-ScaleIn-CPU",
        ServiceNamespace  = "ecs",
        ResourceId        = resource_id,
        ScalableDimension = "ecs:service:DesiredCount",
        PolicyType        = "StepScaling",
        StepScalingPolicyConfiguration = {
            "AdjustmentType":        "ChangeInCapacity",
            "CooldownSeconds":       300,             # wait 5 min before scaling in
            "MetricAggregationType": "Average",
            "StepAdjustments": [
                {
                    "MetricIntervalUpperBound": 0,
                    "ScalingAdjustment":        -1,  # remove 1 task
                }
            ],
        },
    )
    policy_arn = response["PolicyARN"]
    print(f"  -> Scale-IN  policy created (CPU < 30% for 5 min → -1 task)")

    # CloudWatch alarm that triggers scale-in
    cw.put_metric_alarm(
        AlarmName          = "AttritionIQ-CPU-Low-ScaleIn",
        AlarmDescription   = "Scale in ECS when CPU < 30% for 5 min",
        MetricName         = "CPUUtilization",
        Namespace          = "AWS/ECS",
        Dimensions         = [
            {"Name": "ClusterName", "Value": CLUSTER_NAME},
            {"Name": "ServiceName", "Value": SERVICE_NAME},
        ],
        Statistic          = "Average",
        Period             = 60,
        EvaluationPeriods  = 5,
        Threshold          = 30.0,
        ComparisonOperator = "LessThanThreshold",
        AlarmActions       = [policy_arn],
        TreatMissingData   = "notBreaching",
    )
    print(f"     CloudWatch alarm: AttritionIQ-CPU-Low-ScaleIn")
    return policy_arn


if __name__ == "__main__":
    print("=" * 60)
    print("  AttritionIQ — ECS Auto-Scaling Setup")
    print("=" * 60)
    print(f"  Cluster  : {CLUSTER_NAME}")
    print(f"  Service  : {SERVICE_NAME}")
    print(f"  Capacity : {MIN_TASKS} → {MAX_TASKS} tasks")
    print()

    print("[1/3] Registering scalable target...")
    register_scalable_target()

    print("\n[2/3] Creating scale-out policy...")
    create_scale_out_policy()

    print("\n[3/3] Creating scale-in policy...")
    create_scale_in_policy()

    print("\n[DONE] Auto-scaling configured!")
    print("  The ECS service will now automatically:")
    print("  - Add tasks when CPU exceeds 70%")
    print("  - Remove tasks when CPU drops below 30%")
